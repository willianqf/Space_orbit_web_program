// Cliente/game.js

const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');
const loginScreen = document.getElementById('loginScreen');
const hudDiv = document.getElementById('hud');
const shopModal = document.getElementById('shopModal');

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
let mapSize = { w: 8000, h: 8000 };

let camX = 0, camY = 0;
let lastKnownX = 4000, lastKnownY = 4000; 
let respawnBtnRect = { x: 0, y: 0, w: 200, h: 50 };

// --- NOVO: Sistema de Rastro para Auxiliares ---
// Armazena a posição visual atual das auxiliares para fazer o Lerp (suavização)
// Formato: { "PlayerID": [ {x, y}, {x, y}, ... ] }
let auxVisuals = {}; 

// Offsets originais do Python (ships.py)
const AUX_OFFSETS = [
    {x: -40, y: 20}, {x: 40, y: 20}, 
    {x: -50, y: -10}, {x: 50, y: -10}
];

const inputState = { w: false, a: false, s: false, d: false, space: false, mouse_x: 0, mouse_y: 0, mouseDown: false };

function startGame() {
    const name = document.getElementById('playerName').value || "Piloto";
    const mode = document.getElementById('gameMode').value;
    loginScreen.classList.add('hidden');
    hudDiv.classList.remove('hidden');
    connect(name, mode);
}

function toggleShop() { shopModal.classList.toggle('hidden'); }
function buyUpgrade(item) { if(isConnected) socket.send(JSON.stringify({ type: "UPGRADE", item: item })); }
function toggleRegen() { if(isConnected) socket.send(JSON.stringify({ type: "TOGGLE_REGEN" })); }
function requestRespawn() { if(isConnected) socket.send(JSON.stringify({ type: "RESPAWN" })); }

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
    if (!p) return;
    document.getElementById('hudScore').innerText = p.score;
    document.getElementById('hudHp').innerText = p.hp.toFixed(1) + " / " + p.max_hp;
    document.getElementById('hudUpPts').innerText = p.pts_up;
    document.getElementById('shopPointsVal').innerText = p.pts_up;
    updateShopItem('btnMotor', p.nv_motor, 5, 1, p.pts_up);
    updateShopItem('btnDano', p.nv_dano, 5, 1, p.pts_up);
    updateShopItem('btnEscudo', p.nv_escudo, 5, 1, p.pts_up);
    updateShopItem('btnHp', p.nv_hp, 5, 1, p.pts_up);
    updateShopItem('btnAux', p.nv_aux, 4, 1, p.pts_up); 
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
    if (isConnected && myId) {
        let myPlayer = gameState.players.find(p => p.id === myId);
        if (!myPlayer) return;
        const screenCenterX = canvas.width / 2;
        const screenCenterY = canvas.height / 2;
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

// --- Inputs Globais ---
window.addEventListener('keydown', (e) => {
    if(!isConnected) return;
    const k = e.key.toLowerCase();
    if (k === 'v') toggleShop();
    if (k === 'r') toggleRegen();
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
    if (e.target === minimapCanvas || e.target.closest('.hud-btn') || e.target.closest('.shop-panel') || e.target.closest('#loginScreen')) return;

    let myPlayer = gameState.players.find(p => p.id === myId);
    if (!myPlayer) {
        if (inputState.mouse_x >= respawnBtnRect.x && inputState.mouse_x <= respawnBtnRect.x + respawnBtnRect.w &&
            inputState.mouse_y >= respawnBtnRect.y && inputState.mouse_y <= respawnBtnRect.y + respawnBtnRect.h) {
            requestRespawn(); return;
        }
    }
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
    if (!isConnected) return;
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

function drawMinimap() {
    minimapCtx.fillStyle = 'rgba(0, 0, 0, 0.6)';
    minimapCtx.fillRect(0, 0, minimapCanvas.width, minimapCanvas.height);
    const scaleX = minimapCanvas.width / mapSize.w;
    const scaleY = minimapCanvas.height / mapSize.h;
    
    // Borda (sem retângulo de viewport)
    minimapCtx.strokeStyle = '#444'; 
    minimapCtx.lineWidth = 2;
    minimapCtx.strokeRect(0, 0, minimapCanvas.width, minimapCanvas.height);

    // Rota
    let myPlayer = gameState.players.find(p => p.id === myId);
    if (myPlayer && myPlayer.tx !== undefined && myPlayer.ty !== undefined) {
        const startX = myPlayer.x * scaleX;
        const startY = myPlayer.y * scaleY;
        const endX = myPlayer.tx * scaleX;
        const endY = myPlayer.ty * scaleY;
        minimapCtx.beginPath(); minimapCtx.setLineDash([4, 2]); 
        minimapCtx.moveTo(startX, startY); minimapCtx.lineTo(endX, endY);
        minimapCtx.strokeStyle = '#ffffff'; minimapCtx.lineWidth = 1;
        minimapCtx.stroke(); minimapCtx.setLineDash([]);
    }

    gameState.players.forEach(p => {
        minimapCtx.fillStyle = (p.id === myId) ? '#00ff00' : '#ff9900';
        minimapCtx.beginPath(); minimapCtx.arc(p.x * scaleX, p.y * scaleY, 2, 0, Math.PI * 2); minimapCtx.fill();
    });
}

function drawRanking() {
    let sortedPlayers = [...gameState.players].sort((a, b) => b.score - a.score).slice(0, 5);
    let startX = canvas.width - 200;
    let startY = 190; 
    
    ctx.fillStyle = "rgba(0,0,0,0.5)";
    ctx.fillRect(startX - 10, startY - 10, 200, 30 + sortedPlayers.length * 25);
    
    ctx.fillStyle = "#ffcc00";
    ctx.font = "bold 16px Arial";
    ctx.fillText("RANKING", startX + 60, startY + 10);
    
    ctx.font = "14px Arial";
    sortedPlayers.forEach((p, index) => {
        ctx.fillStyle = (p.id === myId) ? "#00ff00" : "#ffffff";
        let name = p.id.split('_')[0];
        if (name.length > 12) name = name.substring(0, 12) + "..";
        ctx.fillText(`${index + 1}. ${name}`, startX, startY + 35 + (index * 25));
        ctx.fillText(`${p.score}`, startX + 140, startY + 35 + (index * 25));
    });
}

// Helper: Rotaciona um ponto (x, y) em torno de (0,0) por um ângulo em Graus
function rotateVector(x, y, angleDegrees) {
    let rad = angleDegrees * Math.PI / 180;
    let cos = Math.cos(rad);
    let sin = Math.sin(rad);
    return {
        x: x * cos - y * sin,
        y: x * sin + y * cos
    };
}

function draw() {
    if (!isConnected) return;
    ctx.fillStyle = '#050505'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    let myPlayer = gameState.players.find(p => p.id === myId);
    
    // --- Lógica de Câmera ---
    if (myPlayer) {
        // Interpolação suave da câmera (opcional, mas fica bom)
        let targetCamX = myPlayer.x - canvas.width / 2;
        let targetCamY = myPlayer.y - canvas.height / 2;
        // Se a câmera estiver muito longe (primeiro frame), pula direto
        if (Math.abs(camX - targetCamX) > 2000) { camX = targetCamX; camY = targetCamY; }
        else {
            camX += (targetCamX - camX) * 0.1;
            camY += (targetCamY - camY) * 0.1;
        }
        lastKnownX = myPlayer.x; lastKnownY = myPlayer.y;
    } else {
        camX = lastKnownX - canvas.width / 2; camY = lastKnownY - canvas.height / 2;
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'; ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = 'red'; ctx.font = 'bold 40px Arial'; ctx.textAlign = 'center';
        ctx.fillText("VOCÊ MORREU", canvas.width/2, canvas.height/2 - 50);
        respawnBtnRect.x = canvas.width/2 - 100; respawnBtnRect.y = canvas.height/2 + 20;
        ctx.fillStyle = '#0099ff'; ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2;
        ctx.fillRect(respawnBtnRect.x, respawnBtnRect.y, respawnBtnRect.w, respawnBtnRect.h);
        ctx.strokeRect(respawnBtnRect.x, respawnBtnRect.y, respawnBtnRect.w, respawnBtnRect.h);
        ctx.fillStyle = 'white'; ctx.font = 'bold 20px Arial';
        ctx.fillText("RESPAWNAR", canvas.width/2, canvas.height/2 + 52);
    }

    // Bordas
    ctx.strokeStyle = '#ff0000'; ctx.lineWidth = 5; ctx.strokeRect(0 - camX, 0 - camY, mapSize.w, mapSize.h);
    
    // Grid
    ctx.strokeStyle = '#1a1a1a'; ctx.lineWidth = 2; 
    const gridSize = 100;
    const offsetX = -camX % gridSize; const offsetY = -camY % gridSize;
    ctx.beginPath();
    for (let x = offsetX; x < canvas.width; x += gridSize) { ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); }
    for (let y = offsetY; y < canvas.height; y += gridSize) { ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); }
    ctx.stroke();

    // --- NPCs (Com Cores Corrigidas) ---
    if (gameState.npcs) {
        gameState.npcs.forEach(npc => {
            const screenX = npc.x - camX; const screenY = npc.y - camY;
            if (screenX < -100 || screenX > canvas.width + 100 || screenY < -100 || screenY > canvas.height + 100) return;
            
            ctx.save();
            ctx.translate(screenX, screenY);

            if (npc.type === 'obstaculo') {
                ctx.fillStyle = '#333'; ctx.beginPath(); ctx.arc(0, 0, npc.size, 0, Math.PI * 2); ctx.fill();
                ctx.strokeStyle = '#555'; ctx.lineWidth = 3; ctx.stroke();
            } else {
                ctx.rotate((npc.angle * Math.PI / 180) * -1);
                
                // --- NOVO: Mapeamento Completo de Cores (PC Version) ---
                let color = '#ff3333'; // Vermelho (Padrão/Perseguidor)
                
                if (npc.type === 'mothership') color = '#00ffff'; // CIANO
                else if (npc.type === 'minion_mothership') color = '#008b8b'; // CIANO ESCURO
                
                else if (npc.type === 'boss_congelante') color = '#0000ff'; // AZUL
                else if (npc.type === 'minion_congelante') color = '#88ccff'; // AZUL CLARO
                
                else if (npc.type === 'bomba') color = '#ffff00'; // AMARELO
                
                else if (npc.type === 'tiro_rapido') color = '#0066cc'; // AZUL TIRO RAPIDO
                else if (npc.type === 'rapido') color = '#ff6600'; // LARANJA
                
                else if (npc.type === 'atordoador') color = '#800080'; // ROXO
                else if (npc.type === 'atirador_rapido') color = '#9900cc'; // ROXO CLARO

                ctx.fillStyle = color; 
                ctx.shadowBlur = 10; ctx.shadowColor = color; // Glow Neon

                if (npc.type.includes('boss') || npc.type === 'mothership') { 
                    ctx.beginPath(); ctx.arc(0, 0, npc.size / 2, 0, Math.PI * 2); ctx.fill(); 
                } else if (npc.type === 'minion_mothership' || npc.type === 'minion_congelante') {
                    // Minions são triângulos pequenos
                    ctx.beginPath(); ctx.moveTo(0, -npc.size/2); ctx.lineTo(-npc.size/2, npc.size/2); ctx.lineTo(npc.size/2, npc.size/2); ctx.fill();
                } else { 
                    ctx.fillRect(-npc.size / 2, -npc.size / 2, npc.size, npc.size); 
                }
                ctx.shadowBlur = 0;

                // Barra de Vida
                if (npc.hp < npc.max_hp) {
                    ctx.rotate(-((npc.angle * Math.PI / 180) * -1)); // Estabiliza
                    ctx.fillStyle = 'red'; ctx.fillRect(-20, 30, 40, 4);
                    ctx.fillStyle = '#00ff00'; 
                    const hpPct = Math.max(0, npc.hp / npc.max_hp);
                    ctx.fillRect(-20, 30, 40 * hpPct, 4);
                }
            }
            ctx.restore();
        });
    }

    // Projéteis
    gameState.projectiles.forEach(p => {
        let color = '#ff5555'; 
        if (p.type && p.type.includes('player')) {
            if (p.type.includes('_max')) color = '#00ff00';
            else color = '#ffff00';
        }
        ctx.shadowBlur = 5; ctx.shadowColor = color; ctx.fillStyle = color;
        ctx.beginPath(); ctx.arc(p.x - camX, p.y - camY, 4, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0;
    });

    // --- JOGADORES (Com Lógica de Auxiliar Aprimorada) ---
    gameState.players.forEach(p => {
        const screenX = p.x - camX; 
        const screenY = p.y - camY;
        
        // 1. Desenha Auxiliares (Antes da nave para ficarem "em baixo" ou ao redor)
        if (p.nv_aux > 0) {
            // Inicializa array de visualização se não existir
            if (!auxVisuals[p.id]) auxVisuals[p.id] = [];
            
            // Garante que o array tenha o tamanho certo
            while (auxVisuals[p.id].length < p.nv_aux) {
                auxVisuals[p.id].push({x: p.x, y: p.y}); // Começa na posição do player
            }

            for (let i = 0; i < p.nv_aux && i < AUX_OFFSETS.length; i++) {
                // Lógica de "Target": Onde a auxiliar DEVERIA estar no mundo
                // Rotaciona o offset baseado no ângulo da nave (p.angle é sentido anti-horário em graus)
                // Math.cos espera radianos. p.angle do Pygame: 0=Dir? Não, Pygame 0=Cima? 
                // No server: angulo = atan2(dy, dx). 0 é Direita. +90 é cima?
                // Vamos usar a função rotateVector helper. O server usa ângulo padrão.
                // Mas lembre: no Pygame y é invertido em relação a cartesiano puro, mas aqui é tela.
                
                // NOTA: O server manda 'angulo' em graus.
                // offset_rotacionado = offset.rotate(-angulo) no python.
                
                let off = AUX_OFFSETS[i];
                let rotOffset = rotateVector(off.x, off.y, -p.angle); 
                let targetWorldX = p.x + rotOffset.x;
                let targetWorldY = p.y + rotOffset.y;

                // Lerp (Suavização)
                let currentAux = auxVisuals[p.id][i];
                currentAux.x += (targetWorldX - currentAux.x) * 0.15; // 0.15 = Velocidade de arrasto
                currentAux.y += (targetWorldY - currentAux.y) * 0.15;

                // Desenha a Auxiliar
                let auxScreenX = currentAux.x - camX;
                let auxScreenY = currentAux.y - camY;

                ctx.save();
                ctx.translate(auxScreenX, auxScreenY);
                // A auxiliar aponta na mesma direção da nave
                ctx.rotate((p.angle * Math.PI / 180) * -1);
                
                ctx.fillStyle = '#00ff66'; // Verde Neon
                ctx.beginPath();
                ctx.moveTo(0, -8);
                ctx.lineTo(-6, 8);
                ctx.lineTo(6, 8);
                ctx.fill();
                ctx.restore();
            }
        }

        // 2. Desenha Nave de Regeneração (NOVO)
        if (p.regen) {
            ctx.save();
            ctx.translate(screenX, screenY);
            
            // Órbita
            let time = Date.now() / 150; // Rápido
            let rx = Math.cos(time) * 50; 
            let ry = Math.sin(time) * 50;
            
            // Desenha a navezinha
            ctx.translate(rx, ry);
            ctx.rotate(time + Math.PI/2); // Gira a navezinha
            
            ctx.fillStyle = '#aa55ff'; // Lilás
            ctx.shadowBlur = 10; ctx.shadowColor = '#aa55ff';
            ctx.beginPath(); 
            ctx.moveTo(0, -10); ctx.lineTo(-8, 8); ctx.lineTo(8, 8); 
            ctx.fill();
            
            ctx.restore();
        }

        // 3. Desenha a Nave Principal
        ctx.save();
        ctx.translate(screenX, screenY);
        
        // Nome e Score
        ctx.fillStyle = 'white'; ctx.font = 'bold 12px Arial'; ctx.textAlign = 'center';
        ctx.fillText(p.id.split('_')[0], 0, -45);
        if (p.score > 0) { ctx.fillStyle = '#ffcc00'; ctx.font = '10px Arial'; ctx.fillText(p.score + " pts", 0, -33); }

        ctx.rotate((p.angle * Math.PI / 180) * -1);
        
        ctx.beginPath(); 
        let color = (p.id === myId) ? '#0088ff' : '#ff8800';
        ctx.fillStyle = color; ctx.shadowBlur = 15; ctx.shadowColor = color;
        ctx.moveTo(0, -20); ctx.lineTo(-15, 20); ctx.lineTo(15, 20); ctx.closePath(); ctx.fill(); 
        ctx.shadowBlur = 0;

        // Barra de Vida
        ctx.rotate(-((p.angle * Math.PI / 180) * -1)); // Estabiliza
        ctx.fillStyle = 'red'; ctx.fillRect(-25, 30, 50, 6);
        ctx.fillStyle = '#00ff00'; const hpPercent = Math.max(0, p.hp / p.max_hp);
        ctx.fillRect(-25, 30, 50 * hpPercent, 6);
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 1; ctx.strokeRect(-25, 30, 50, 6);
        
        // Efeito de Escudo (Arco Frontal)
        if (p.shield_hit) {
            ctx.beginPath();
            ctx.arc(0, 0, 40, -Math.PI/4, Math.PI/4); // Arco frontal
            ctx.strokeStyle = 'rgba(0, 255, 255, 0.8)';
            ctx.lineWidth = 5;
            ctx.stroke();
        }

        ctx.restore();
    });
    
    drawMinimap(); 
    drawRanking(); 
    requestAnimationFrame(draw);
}