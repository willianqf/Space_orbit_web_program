// Cliente/game.js

const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');
const loginScreen = document.getElementById('loginScreen');
const hudDiv = document.getElementById('hud');
const shopModal = document.getElementById('shopModal');
const pauseMenu = document.getElementById('pauseMenu');

const btnResume = document.getElementById('btnResume');
const btnRespawn = document.getElementById('btnRespawn');
const btnSpectate = document.getElementById('btnSpectate');

const minimapCanvas = document.getElementById('minimapCanvas');
const minimapCtx = minimapCanvas.getContext('2d');

canvas.width = window.innerWidth;
canvas.height = window.innerHeight;
minimapCanvas.width = 150;
minimapCanvas.height = 150;

window.addEventListener('resize', () => {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
});

const SERVER_URL = 'ws://localhost:8765';
let socket = null;
let myId = null;
let isConnected = false;
let gameState = { players: [], projectiles: [], npcs: [] };
let visualState = { players: {}, projectiles: {}, npcs: {} };

let mapSize = { w: 8000, h: 8000 };

let camX = 0, camY = 0;
let lastKnownX = 4000, lastKnownY = 4000; 
let respawnBtnRect = { x: 0, y: 0, w: 200, h: 50 };

let isPaused = false;
let isSpectating = false;
let spectatorTargetId = null;

let auxVisuals = {}; 
const AUX_OFFSETS = [
    {x: -40, y: 20}, {x: 40, y: 20}, 
    {x: -50, y: -10}, {x: 50, y: -10}
];
const AUX_COSTS = [1, 2, 3, 4];

let particles = []; 

const inputState = { w: false, a: false, s: false, d: false, space: false, mouse_x: 0, mouse_y: 0, mouseDown: false };

function lerp(start, end, t) { return start + (end - start) * t; }
function lerpAngle(start, end, t) {
    let diff = end - start;
    if (diff > 180) diff -= 360;
    if (diff < -180) diff += 360;
    return start + diff * t;
}

function spawnEngineParticles(x, y, angle) {
    const rad = (angle * Math.PI) / 180;
    // Ajuste fino da posição do motor
    const dist = 28; 
    const backX = x + Math.sin(rad) * dist;
    const backY = y + Math.cos(rad) * dist;
    
    const spread = 4;
    const varX = (Math.random() - 0.5) * spread;
    const varY = (Math.random() - 0.5) * spread;

    particles.push({
        x: backX + varX,
        y: backY + varY,
        life: 1.0, 
        size: 5 + Math.random() * 5
    });
}

function updateAndDrawParticles() {
    for (let i = particles.length - 1; i >= 0; i--) {
        let p = particles[i];
        p.life -= 0.08; 
        if (p.life <= 0) {
            particles.splice(i, 1);
            continue;
        }
        let screenX = p.x - camX;
        let screenY = p.y - camY;
        ctx.beginPath();
        ctx.arc(screenX, screenY, p.size * p.life, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255, ${Math.floor(150 * p.life)}, 0, ${p.life})`;
        ctx.fill();
    }
}

function startGame() {
    const name = document.getElementById('playerName').value || "Piloto";
    const mode = document.getElementById('gameMode').value;
    loginScreen.classList.add('hidden');
    hudDiv.classList.remove('hidden');
    connect(name, mode);
}

function toggleShop() { if(!isPaused) shopModal.classList.toggle('hidden'); }
function buyUpgrade(item) { if(isConnected) socket.send(JSON.stringify({ type: "UPGRADE", item: item })); }
function toggleRegen() { if(isConnected && !isPaused) socket.send(JSON.stringify({ type: "TOGGLE_REGEN" })); }

function togglePause() {
    isPaused = !isPaused;
    if (isPaused) {
        pauseMenu.classList.remove('hidden');
        let myPlayer = gameState.players.find(p => p.id === myId);
        if (isSpectating || !myPlayer || myPlayer.hp <= 0) {
            btnResume.innerText = "VOLTAR (FECHAR MENU)";
            btnResume.classList.remove('hidden');
            btnRespawn.classList.remove('hidden');
            btnSpectate.classList.add('hidden');
        } else {
            btnResume.innerText = "VOLTAR AO JOGO";
            btnResume.classList.remove('hidden');
            btnRespawn.classList.add('hidden');
            btnSpectate.classList.remove('hidden');
        }
    } else {
        pauseMenu.classList.add('hidden');
    }
}

function enterSpectatorMode() { if (isConnected) { isSpectating = true; socket.send(JSON.stringify({ type: "ENTER_SPECTATOR" })); togglePause(); } }
function requestRespawn() { if (isConnected) { isSpectating = false; socket.send(JSON.stringify({ type: "RESPAWN" })); if (isPaused) { isPaused = false; pauseMenu.classList.add('hidden'); } } }
function exitGame() { if (socket) socket.close(); location.reload(); }

function connect(playerName, gameMode) {
    socket = new WebSocket(SERVER_URL);
    socket.onopen = () => { socket.send(JSON.stringify({ type: "LOGIN", name: playerName, mode: gameMode })); };
    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "WELCOME") {
            myId = msg.id; isConnected = true;
            if (msg.map_width) mapSize.w = msg.map_width;
            if (msg.map_height) mapSize.h = msg.map_height;
            setInterval(sendInput, 1000 / 30);
            requestAnimationFrame(draw);
        } else if (msg.type === "STATE") {
            gameState = msg;
            updateHud();
        }
    };
    socket.onclose = () => { isConnected = false; alert("Desconectado."); location.reload(); };
}

function updateHud() {
    let p = gameState.players.find(p => p.id === myId);
    if (!p) { document.getElementById('hudHp').innerText = "ESPECTADOR"; return; }
    document.getElementById('hudScore').innerText = p.score;
    document.getElementById('hudHp').innerText = p.hp.toFixed(1) + " / " + p.max_hp;
    document.getElementById('hudUpPts').innerText = p.pts_up;
    document.getElementById('shopPointsVal').innerText = p.pts_up;
    let auxCost = (p.nv_aux < 4) ? AUX_COSTS[p.nv_aux] : 0;
    updateShopItem('btnMotor', p.nv_motor, 5, 1, p.pts_up);
    updateShopItem('btnDano', p.nv_dano, 5, 1, p.pts_up);
    updateShopItem('btnEscudo', p.nv_escudo, 5, 1, p.pts_up);
    updateShopItem('btnHp', p.nv_hp, 5, 1, p.pts_up);
    updateShopItem('btnAux', p.nv_aux, 4, auxCost, p.pts_up); 
}

function updateShopItem(elemId, currentLvl, maxLvl, cost, playerPts) {
    const el = document.getElementById(elemId);
    const lvlDiv = el.querySelector('.shop-level');
    const costDiv = el.querySelector('.shop-cost');
    if (currentLvl >= maxLvl) {
        lvlDiv.innerText = "MAX"; lvlDiv.style.color = "#ff00ff"; costDiv.innerText = "-"; el.classList.add('disabled');
    } else {
        lvlDiv.innerText = `Nv: ${currentLvl}/${maxLvl}`; lvlDiv.style.color = "#00ffff"; costDiv.innerText = `Custo: ${cost}`;
        if (playerPts < cost) el.classList.add('disabled'); else el.classList.remove('disabled');
    }
}

function sendInput() {
    if (isPaused || isSpectating) return;
    if (isConnected && myId) {
        let myPlayer = gameState.players.find(p => p.id === myId);
        if (!myPlayer) return;
        let worldMouseX = camX + inputState.mouse_x;
        let worldMouseY = camY + inputState.mouse_y;
        const inputPacket = { type: "INPUT", w: inputState.w, a: inputState.a, s: inputState.s, d: inputState.d, space: inputState.space };
        if (inputState.mouseDown) {
            inputPacket.mouse_x = Math.floor(worldMouseX);
            inputPacket.mouse_y = Math.floor(worldMouseY);
        }
        socket.send(JSON.stringify(inputPacket));
    }
}

window.addEventListener('keydown', (e) => {
    if(!isConnected) return;
    const k = e.key.toLowerCase();
    if (k === 'escape') { togglePause(); return; }
    if (isPaused) return; 
    if (k === 'v') toggleShop();
    if (k === 'r') toggleRegen();
    if (isSpectating && (k === 'e' || k === 'q')) cycleSpectatorTarget();
    if (k === 'w' || k === 'arrowup') inputState.w = true;
    if (k === 'a' || k === 'arrowleft') inputState.a = true;
    if (k === 's' || k === 'arrowdown') inputState.s = true;
    if (k === 'd' || k === 'arrowright') inputState.d = true;
    if (k === ' ') inputState.space = true;
});
window.addEventListener('keyup', (e) => {
    if(!isConnected) return;
    const k = e.key.toLowerCase();
    if (k === 'w' || k === 'arrowup') inputState.w = false;
    if (k === 'a' || k === 'arrowleft') inputState.a = false;
    if (k === 's' || k === 'arrowdown') inputState.s = false;
    if (k === 'd' || k === 'arrowright') inputState.d = false;
    if (k === ' ') inputState.space = false;
});
window.addEventListener('mousemove', (e) => { inputState.mouse_x = e.clientX; inputState.mouse_y = e.clientY; });
window.addEventListener('mousedown', (e) => {
    if (!isConnected) return;
    if (e.target.closest('.hud-btn') || e.target.closest('.shop-panel') || e.target.closest('#loginScreen') || e.target.closest('.pause-box')) return;
    let myPlayer = gameState.players.find(p => p.id === myId);
    if (!myPlayer || isSpectating) {
        if (!isSpectating && !isPaused) {
             if (inputState.mouse_x >= respawnBtnRect.x && inputState.mouse_x <= respawnBtnRect.x + respawnBtnRect.w &&
                inputState.mouse_y >= respawnBtnRect.y && inputState.mouse_y <= respawnBtnRect.y + respawnBtnRect.h) {
                requestRespawn(); return;
            }
        }
        if (e.button === 0) cycleSpectatorTarget();
        return;
    }
    if (isPaused) return;
    if (e.button === 0) inputState.mouseDown = true;
    if (e.button === 2) {
        let worldMouseX = camX + e.clientX;
        let worldMouseY = camY + e.clientY;
        socket.send(JSON.stringify({ type: "TARGET", x: Math.floor(worldMouseX), y: Math.floor(worldMouseY) }));
    }
});
window.addEventListener('mouseup', (e) => { if (e.button === 0) inputState.mouseDown = false; });
window.addEventListener('contextmenu', (e) => { e.preventDefault(); return false; });
minimapCanvas.addEventListener('mousedown', (e) => {
    if (!isConnected || isPaused || isSpectating) return;
    e.stopPropagation(); e.preventDefault();
    if (e.button !== 0 && e.button !== 2) return;
    const rect = minimapCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const scaleX = mapSize.w / minimapCanvas.width;
    const scaleY = mapSize.h / minimapCanvas.height;
    const worldX = Math.floor(x * scaleX);
    const worldY = Math.floor(y * scaleY);
    socket.send(JSON.stringify({ type: "INPUT", mouse_x: worldX, mouse_y: worldY }));
});

function cycleSpectatorTarget() {
    if (gameState.players.length === 0) return;
    let currentIndex = -1;
    if (spectatorTargetId) currentIndex = gameState.players.findIndex(p => p.id === spectatorTargetId);
    let nextIndex = (currentIndex + 1) % gameState.players.length;
    spectatorTargetId = gameState.players[nextIndex].id;
}

function drawMinimap() {
    minimapCtx.fillStyle = 'rgba(0, 0, 0, 0.6)'; minimapCtx.fillRect(0, 0, minimapCanvas.width, minimapCanvas.height);
    const scaleX = minimapCanvas.width / mapSize.w; const scaleY = minimapCanvas.height / mapSize.h;
    minimapCtx.strokeStyle = '#444'; minimapCtx.lineWidth = 2; minimapCtx.strokeRect(0, 0, minimapCanvas.width, minimapCanvas.height);
    let myPlayer = gameState.players.find(p => p.id === myId);
    if (myPlayer && myPlayer.tx !== undefined && myPlayer.ty !== undefined) {
        const startX = myPlayer.x * scaleX; const startY = myPlayer.y * scaleY; const endX = myPlayer.tx * scaleX; const endY = myPlayer.ty * scaleY;
        minimapCtx.beginPath(); minimapCtx.setLineDash([4, 2]); minimapCtx.moveTo(startX, startY); minimapCtx.lineTo(endX, endY);
        minimapCtx.strokeStyle = '#ffffff'; minimapCtx.lineWidth = 1; minimapCtx.stroke(); minimapCtx.setLineDash([]);
    }
    gameState.players.forEach(p => {
        minimapCtx.fillStyle = (p.id === myId) ? '#00ff00' : '#ff9900';
        minimapCtx.beginPath(); minimapCtx.arc(p.x * scaleX, p.y * scaleY, 2, 0, Math.PI * 2); minimapCtx.fill();
    });
}

function drawRanking() {
    let sortedPlayers = [...gameState.players].sort((a, b) => b.score - a.score).slice(0, 5);
    let startX = canvas.width - 200; let startY = 190; 
    ctx.fillStyle = "rgba(0,0,0,0.5)"; ctx.fillRect(startX - 10, startY - 10, 200, 30 + sortedPlayers.length * 25);
    ctx.fillStyle = "#ffcc00"; ctx.font = "bold 16px Arial"; ctx.fillText("RANKING", startX + 60, startY + 10);
    ctx.font = "14px Arial";
    sortedPlayers.forEach((p, index) => {
        ctx.fillStyle = (p.id === myId) ? "#00ff00" : "#ffffff";
        let name = p.id.split('_')[0]; if (name.length > 12) name = name.substring(0, 12) + "..";
        ctx.fillText(`${index + 1}. ${name}`, startX, startY + 35 + (index * 25));
        ctx.fillText(`${p.score}`, startX + 140, startY + 35 + (index * 25));
    });
}

function rotateVector(x, y, angleDegrees) {
    let rad = angleDegrees * Math.PI / 180;
    let cos = Math.cos(rad);
    let sin = Math.sin(rad);
    return { x: x * cos - y * sin, y: x * sin + y * cos };
}

function draw() {
    if (!isConnected) return;
    ctx.fillStyle = '#050505'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    const lerpFactor = 0.2; 
    
    gameState.players.forEach(p => {
        if (!visualState.players[p.id]) { visualState.players[p.id] = { x: p.x, y: p.y, angle: p.angle, prevX: p.x, prevY: p.y }; }
        else {
            let v = visualState.players[p.id];
            v.prevX = v.x; v.prevY = v.y;
            v.x = lerp(v.x, p.x, lerpFactor); 
            v.y = lerp(v.y, p.y, lerpFactor); 
            v.angle = lerpAngle(v.angle, p.angle, lerpFactor);
        }
    });
    for (let id in visualState.players) { if (!gameState.players.find(p => p.id === id)) { delete visualState.players[id]; } }

    let myPlayer = gameState.players.find(p => p.id === myId);
    let myVisual = visualState.players[myId];
    let targetCamX, targetCamY;

    if (myPlayer) {
        targetCamX = myVisual.x - canvas.width / 2; targetCamY = myVisual.y - canvas.height / 2;
        lastKnownX = myVisual.x; lastKnownY = myVisual.y;
        if (Math.abs(camX - targetCamX) > 2000) { camX = targetCamX; camY = targetCamY; }
        else { camX += (targetCamX - camX) * 0.1; camY += (targetCamY - camY) * 0.1; }
    } else {
        if (isSpectating) {
            let target = gameState.players.find(p => p.id === spectatorTargetId);
            if (!target && gameState.players.length > 0) { spectatorTargetId = gameState.players[0].id; target = gameState.players[0]; }
            if (target) {
                let targetVisual = visualState.players[target.id] || target;
                targetCamX = targetVisual.x - canvas.width / 2; targetCamY = targetVisual.y - canvas.height / 2;
                camX += (targetCamX - camX) * 0.1; camY += (targetCamY - camY) * 0.1;
                ctx.fillStyle = 'rgba(0,0,0,0.5)'; ctx.fillRect(canvas.width/2 - 150, 10, 300, 30);
                ctx.fillStyle = '#00ffff'; ctx.font = '16px Arial'; ctx.textAlign = 'center';
                ctx.fillText(`Assistindo: ${target.id.split('_')[0]} | [Q]/[E] ou Clique para trocar`, canvas.width/2, 30);
            } else {
                camX = lastKnownX - canvas.width / 2; camY = lastKnownY - canvas.height / 2;
                ctx.fillStyle = '#aaa'; ctx.font = '20px Arial'; ctx.textAlign = 'center'; ctx.fillText("Nenhum jogador ativo...", canvas.width/2, canvas.height/2);
            }
        } else {
            camX = lastKnownX - canvas.width / 2; camY = lastKnownY - canvas.height / 2;
            ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'; ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = 'red'; ctx.font = 'bold 40px Arial'; ctx.textAlign = 'center'; ctx.fillText("VOCÊ MORREU", canvas.width/2, canvas.height/2 - 50);
            if (!isPaused) {
                respawnBtnRect.x = canvas.width/2 - 100; respawnBtnRect.y = canvas.height/2 + 20;
                ctx.fillStyle = '#0099ff'; ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2;
                ctx.fillRect(respawnBtnRect.x, respawnBtnRect.y, respawnBtnRect.w, respawnBtnRect.h);
                ctx.strokeRect(respawnBtnRect.x, respawnBtnRect.y, respawnBtnRect.w, respawnBtnRect.h);
                ctx.fillStyle = 'white'; ctx.font = 'bold 20px Arial'; ctx.fillText("RESPAWNAR", canvas.width/2, canvas.height/2 + 52);
            }
        }
    }

    ctx.strokeStyle = '#ff0000'; ctx.lineWidth = 5; ctx.strokeRect(0 - camX, 0 - camY, mapSize.w, mapSize.h);
    ctx.strokeStyle = '#1a1a1a'; ctx.lineWidth = 2; const gridSize = 100;
    const offsetX = -camX % gridSize; const offsetY = -camY % gridSize;
    ctx.beginPath();
    for (let x = offsetX; x < canvas.width; x += gridSize) { ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); }
    for (let y = offsetY; y < canvas.height; y += gridSize) { ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); }
    ctx.stroke();

    updateAndDrawParticles();

    if (gameState.npcs) {
        gameState.npcs.forEach(npc => {
            if (!visualState.npcs[npc.id]) { visualState.npcs[npc.id] = { x: npc.x, y: npc.y, angle: npc.angle }; }
            else {
                let v = visualState.npcs[npc.id];
                v.x = lerp(v.x, npc.x, lerpFactor); v.y = lerp(v.y, npc.y, lerpFactor); v.angle = lerpAngle(v.angle, npc.angle, lerpFactor);
            }
            let v = visualState.npcs[npc.id];
            const screenX = v.x - camX; const screenY = v.y - camY;
            if (screenX < -200 || screenX > canvas.width + 200 || screenY < -200 || screenY > canvas.height + 200) return;
            
            ctx.save(); ctx.translate(screenX, screenY);
            if (npc.type === 'obstaculo') {
                ctx.fillStyle = '#333'; ctx.beginPath(); ctx.arc(0, 0, npc.size, 0, Math.PI * 2); ctx.fill();
                ctx.strokeStyle = '#555'; ctx.lineWidth = 3; ctx.stroke();
            } else {
                ctx.rotate((v.angle * Math.PI / 180) * -1);
                let color = '#ff3333'; 
                if (npc.type === 'mothership') color = '#00ffff'; 
                else if (npc.type === 'minion_mothership') color = '#008b8b'; 
                else if (npc.type === 'boss_congelante') color = '#0000ff'; 
                else if (npc.type === 'minion_congelante') color = '#88ccff'; 
                else if (npc.type === 'bomba') color = '#ffff00'; 
                else if (npc.type === 'tiro_rapido') color = '#0066cc'; 
                else if (npc.type === 'rapido') color = '#ff6600'; 
                else if (npc.type === 'atordoador') color = '#800080'; 
                else if (npc.type === 'atirador_rapido') color = '#9900cc'; 
                ctx.fillStyle = color; ctx.shadowBlur = 10; ctx.shadowColor = color; 
                if (npc.type === 'mothership') { ctx.fillRect(-npc.size / 2, -npc.size / 2, npc.size, npc.size); } 
                else if (npc.type === 'boss_congelante') { ctx.beginPath(); ctx.arc(0, 0, npc.size / 2, 0, Math.PI * 2); ctx.fill(); ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 3; ctx.stroke(); } 
                else if (npc.type.includes('minion')) { ctx.beginPath(); ctx.moveTo(0, -npc.size/2); ctx.lineTo(-npc.size/2, npc.size/2); ctx.lineTo(npc.size/2, npc.size/2); ctx.fill(); } 
                else { ctx.fillRect(-npc.size / 2, -npc.size / 2, npc.size, npc.size); }
                ctx.shadowBlur = 0;
                if (npc.hp < npc.max_hp) {
                    ctx.rotate(-((v.angle * Math.PI / 180) * -1)); 
                    ctx.fillStyle = 'red'; ctx.fillRect(-20, 30, 40, 4);
                    ctx.fillStyle = '#00ff00'; const hpPct = Math.max(0, npc.hp / npc.max_hp);
                    ctx.fillRect(-20, 30, 40 * hpPct, 4);
                }
            }
            ctx.restore();
        });
        for (let id in visualState.npcs) { if (!gameState.npcs.find(n => n.id === id)) delete visualState.npcs[id]; }
    }

    gameState.projectiles.forEach(p => {
        let color = '#ff5555'; 
        let isMax = false;
        
        if (p.type && p.type.includes('player')) { 
            if (p.type.includes('_max')) { color = '#00ff00'; isMax = true; } 
            else color = '#ffff00'; 
        }
        
        ctx.beginPath(); 
        ctx.arc(p.x - camX, p.y - camY, 4, 0, Math.PI * 2); 
        
        if (isMax) { 
            // CORREÇÃO: Tiro Neon Verde Vibrante
            ctx.arc(p.x - camX, p.y - camY, 6, 0, Math.PI * 2);
            ctx.shadowBlur = 50; 
            ctx.shadowColor = '#00ff00'; 
            ctx.fillStyle = '#00ff00'; // Base Verde
            ctx.fill();
            
            // Núcleo Branco para parecer brilhante
            ctx.beginPath();
            ctx.arc(p.x - camX, p.y - camY, 2, 0, Math.PI * 2);
            ctx.fillStyle = '#ffffff';
            ctx.fill();
        } else { 
            ctx.shadowBlur = 5; ctx.shadowColor = color; ctx.fillStyle = color; 
            ctx.fill(); 
        }
        ctx.shadowBlur = 0;
    });

    gameState.players.forEach(p => {
        let v = visualState.players[p.id] || p;
        const screenX = v.x - camX; const screenY = v.y - camY;
        
        let speed = 0;
        if (v.prevX !== undefined) {
            let dx = v.x - v.prevX; let dy = v.y - v.prevY;
            speed = Math.sqrt(dx*dx + dy*dy);
        }
        v.prevX = v.x; v.prevY = v.y;

        if (p.nv_motor >= 5 && speed > 0.5) { spawnEngineParticles(v.x, v.y, v.angle); }

        if (p.nv_aux > 0) {
            if (!auxVisuals[p.id]) auxVisuals[p.id] = [];
            while (auxVisuals[p.id].length < p.nv_aux) { auxVisuals[p.id].push({x: v.x, y: v.y}); }
            for (let i = 0; i < p.nv_aux && i < AUX_OFFSETS.length; i++) {
                let off = AUX_OFFSETS[i]; let rotOffset = rotateVector(off.x, off.y, -v.angle); 
                let targetWorldX = v.x + rotOffset.x; let targetWorldY = v.y + rotOffset.y;
                let currentAux = auxVisuals[p.id][i];
                currentAux.x += (targetWorldX - currentAux.x) * 0.15; currentAux.y += (targetWorldY - currentAux.y) * 0.15;
                let auxScreenX = currentAux.x - camX; let auxScreenY = currentAux.y - camY;
                ctx.save(); ctx.translate(auxScreenX, auxScreenY); ctx.rotate((v.angle * Math.PI / 180) * -1);
                ctx.fillStyle = '#00ff66'; ctx.beginPath(); ctx.moveTo(0, -8); ctx.lineTo(-6, 8); ctx.lineTo(6, 8); ctx.fill(); ctx.restore();
            }
        }
        if (p.regen) {
            ctx.save(); ctx.translate(screenX, screenY);
            let time = Date.now() / 150; let rx = Math.cos(time) * 50; let ry = Math.sin(time) * 50;
            ctx.translate(rx, ry); ctx.rotate(time + Math.PI/2); 
            ctx.fillStyle = '#aa55ff'; ctx.shadowBlur = 10; ctx.shadowColor = '#aa55ff';
            ctx.beginPath(); ctx.moveTo(0, -10); ctx.lineTo(-8, 8); ctx.lineTo(8, 8); ctx.fill(); ctx.restore();
        }
        ctx.save(); ctx.translate(screenX, screenY);
        
        // --- CORREÇÃO: ESCUDO DESENHADO AQUI (ANTES DA ROTAÇÃO DA NAVE) ---
        if (p.shield_hit) {
            if (p.shield_angle !== undefined) {
                 ctx.save();
                 ctx.rotate(p.shield_angle); // Usa ângulo absoluto do servidor
                 ctx.beginPath(); ctx.arc(0, 0, 40, -Math.PI/4, Math.PI/4); 
                 ctx.strokeStyle = 'rgba(0, 255, 255, 0.8)'; ctx.lineWidth = 5; ctx.stroke();
                 ctx.restore();
            }
        }
        // ------------------------------------------------------------------

        ctx.fillStyle = 'white'; ctx.font = 'bold 12px Arial'; ctx.textAlign = 'center';
        ctx.fillText(p.id.split('_')[0], 0, -45);
        if (p.score > 0) { ctx.fillStyle = '#ffcc00'; ctx.font = '10px Arial'; ctx.fillText(p.score + " pts", 0, -33); }
        
        ctx.rotate((v.angle * Math.PI / 180) * -1);
        ctx.beginPath(); let color = (p.id === myId) ? '#0088ff' : '#ff8800';
        ctx.fillStyle = color; ctx.shadowBlur = 15; ctx.shadowColor = color;
        ctx.moveTo(0, -20); ctx.lineTo(-15, 20); ctx.lineTo(15, 20); ctx.closePath(); ctx.fill(); ctx.shadowBlur = 0;
        
        // Barra de Vida
        ctx.rotate(-((v.angle * Math.PI / 180) * -1)); 
        ctx.fillStyle = 'red'; ctx.fillRect(-25, 30, 50, 6);
        ctx.fillStyle = '#00ff00'; const hpPercent = Math.max(0, p.hp / p.max_hp);
        ctx.fillRect(-25, 30, 50 * hpPercent, 6);
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 1; ctx.strokeRect(-25, 30, 50, 6);
        
        ctx.restore();
    });
    
    drawMinimap(); 
    drawRanking(); 
    requestAnimationFrame(draw);
}