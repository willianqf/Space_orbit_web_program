# Servidor/server_ws.py
import asyncio
import websockets
import json
import time
import random
import math
import traceback 
import settings as s
import multi.pvp_settings as pvp_s
import server_bot_ai

from server_logic import (
    server_calcular_posicao_spawn, server_comprar_upgrade, update_player_logic,
    update_projectile_physics, update_npc_generic_logic, update_mothership_logic,
    update_boss_congelante_logic, update_minion_logic, calc_hit_angle_rad,
    server_spawnar_inimigo_aleatorio, server_spawnar_mothership, 
    server_spawnar_boss_congelante, server_spawnar_minion_mothership,
    server_spawnar_minion_congelante, server_spawnar_obstaculo, server_ganhar_pontos,
    process_auxiliaries_logic, 
    COOLDOWN_TIRO, MAX_PLAYERS_PVE, MAX_PLAYERS_PVP, REGEN_TICK_RATE_MS, 
    REGEN_POR_TICK, PONTOS_LIMIARES_PARA_UPGRADE, VIDA_POR_NIVEL, 
    MAX_DISTANCIA_TIRO_SQ, REDUCAO_DANO_POR_NIVEL, COLISAO_JOGADOR_PROJ_DIST_SQ,
    TARGET_CLICK_SIZE_SQ, COLISAO_JOGADOR_NPC_DIST_SQ,
    AUX_POSICOES, AUX_COOLDOWN_TIRO, AUX_DISTANCIA_TIRO_SQ, _rotate_vector,
    QTD_SALAS_PVE, QTD_SALAS_PVP
)

PORT = 8765 
TICK_RATE = 30 
REFERENCE_FPS = 60.0 

# Limite técnico de conexões por sala
MAX_CONEXOES_PVP = 20 

class GameRoom:
    def __init__(self, room_id, game_mode, max_players):
        self.room_id = room_id
        self.game_mode = game_mode
        self.max_players = max_players 
        self.clients = set() 
        self.players = {}    
        self.projectiles = []
        self.npcs = []
        self.obstaculos = [] 
        self.next_npc_id = 0
        self.agora_ms = 0
        
        self.state_globals = {'player_states': self.players, 'network_npcs': self.npcs}
        self.logic_callbacks = {'spawn_calculator': server_calcular_posicao_spawn, 'upgrade_purchaser': server_comprar_upgrade}
        
        if game_mode == "PVE":
            self.bot_manager = server_bot_ai.ServerBotManager(s, self.state_globals, self.logic_callbacks)

    def is_full(self):
        return len(self.clients) >= self.max_players

    def has_spectator_slot(self):
        limit = MAX_CONEXOES_PVP if self.game_mode == "PVP" else MAX_PLAYERS_PVE
        return len(self.clients) < limit

    async def broadcast(self, message_dict):
        if not self.clients: return
        message_str = json.dumps(message_dict)
        
        tasks = []
        for client in self.clients:
            # --- PROTEÇÃO CONTRA LENTIDÃO DE CLIENTE ---
            # Se o cliente não ler os dados rápido o suficiente, pulamos o envio para não travar o servidor
            try:
                if client.transport and client.transport.get_write_buffer_size() > 65536:
                    continue 
            except: pass
            
            tasks.append(client.send(message_str))
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def remove_player(self, websocket):
        if websocket in self.clients:
            self.clients.remove(websocket)
            if websocket in self.players:
                del self.players[websocket]

    def update(self, dt_multiplier=1.0):
        pass

    def get_state_json(self):
        return {}

class PveRoom(GameRoom):
    def __init__(self, room_id):
        super().__init__(room_id, "PVE", MAX_PLAYERS_PVE)
        self.last_bot_check = 0

    def update(self, dt_multiplier=1.0):
        self.agora_ms = int(time.time() * 1000)
        
        # --- SPAWN DE NPCS ---
        count_normais = sum(1 for n in self.npcs if n.get('hp') > 0 and n['tipo'] not in ['mothership', 'boss_congelante', 'minion_mothership', 'minion_congelante', 'obstaculo'])
        count_motherships = sum(1 for n in self.npcs if n.get('hp') > 0 and n['tipo'] == 'mothership')
        count_bosses = sum(1 for n in self.npcs if n.get('hp') > 0 and n['tipo'] == 'boss_congelante')
        
        precisa_spawnar = (count_normais < s.MAX_INIMIGOS) or (count_motherships < s.MAX_MOTHERSHIPS) or (count_bosses < s.MAX_BOSS_CONGELANTE)
        
        if precisa_spawnar:
            refs = [(p['x'], p['y']) for p in self.players.values()]

            if count_normais < s.MAX_INIMIGOS:
                npc = server_spawnar_inimigo_aleatorio(0, 0, f"npc_{self.next_npc_id}")
                sx, sy = server_calcular_posicao_spawn(refs, s.MAP_WIDTH, s.MAP_HEIGHT)
                npc['x'], npc['y'] = sx, sy; self.npcs.append(npc); self.next_npc_id += 1
            
            if count_motherships < s.MAX_MOTHERSHIPS:
                ms = server_spawnar_mothership(0, 0, f"ms_{self.next_npc_id}")
                sx, sy = server_calcular_posicao_spawn(refs, s.MAP_WIDTH, s.MAP_HEIGHT)
                ms['x'], ms['y'] = sx, sy; self.npcs.append(ms); self.next_npc_id += 1
            
            if count_bosses < s.MAX_BOSS_CONGELANTE:
                boss = server_spawnar_boss_congelante(0, 0, f"boss_{self.next_npc_id}")
                sx, sy = server_calcular_posicao_spawn(refs, s.MAP_WIDTH, s.MAP_HEIGHT)
                boss['x'], boss['y'] = sx, sy; self.npcs.append(boss); self.next_npc_id += 1

        # --- GERENCIAMENTO DE BOTS (OTIMIZADO) ---
        if self.agora_ms - self.last_bot_check > 1000:
            self.last_bot_check = self.agora_ms
            humanos_ativos_count = sum(1 for p in self.players.values() if not p.get('is_bot') and not p.get('is_spectator'))
            slots_para_bots = max(0, 10 - humanos_ativos_count)
            target_bots = min(s.MAX_BOTS, slots_para_bots)
            
            bots_remover = self.bot_manager.manage_bot_population(target_bots)
            for bot_key in bots_remover:
                key_to_delete = next((k for k, v in self.players.items() if v['nome'] == bot_key and v.get('is_bot')), None)
                if key_to_delete: del self.players[key_to_delete]

        self._update_game_logic(dt_multiplier)
        self.npcs[:] = [n for n in self.npcs if n.get('hp') > 0]

    def _update_game_logic(self, dt):
        living_players = [p for p in self.players.values() if p.get('hp') > 0 and not p.get('is_spectator')]
        
        if len(self.obstaculos) < s.MAX_OBSTACULOS:
            refs = [(p['x'], p['y']) for p in self.players.values()]
            obs = server_spawnar_obstaculo(refs, s.MAP_WIDTH, s.MAP_HEIGHT, f"obs_{self.next_npc_id}")
            self.obstaculos.append(obs); self.next_npc_id += 1

        living_targets = living_players + self.npcs + self.obstaculos
        novos_projeteis = []

        for p in living_players:
            if p.get('is_bot'): self.bot_manager.process_bot_logic(p, living_players, self.agora_ms)
            if p.get('esta_regenerando'):
                if (p['teclas']['w'] or p['teclas']['a'] or p['teclas']['s'] or p['teclas']['d'] or p['alvo_mouse']): p['esta_regenerando'] = False
                elif p['hp'] < p['max_hp']:
                    if self.agora_ms - p.get('ultimo_tick_regeneracao', 0) > REGEN_TICK_RATE_MS:
                        p['hp'] = min(p['max_hp'], p['hp'] + REGEN_POR_TICK); p['ultimo_tick_regeneracao'] = self.agora_ms
                else: p['esta_regenerando'] = False

            new_proj = update_player_logic(p, living_targets, self.agora_ms, s.MAP_WIDTH, s.MAP_HEIGHT, dt)
            if new_proj: novos_projeteis.append(new_proj)
            aux_projs = process_auxiliaries_logic(p, living_targets, self.agora_ms)
            if aux_projs: novos_projeteis.extend(aux_projs)

        for npc in self.npcs[:]: 
            if npc.get('hp') <= 0: continue
            new_proj = None
            if npc['tipo'] == 'mothership': update_mothership_logic(npc, self.players, self.agora_ms, self, dt)
            elif npc['tipo'] == 'boss_congelante': new_proj = update_boss_congelante_logic(npc, self.players, self.agora_ms, self, dt)
            elif 'minion' in npc['tipo']: new_proj = update_minion_logic(npc, self.players, self.agora_ms, self, dt)
            else: new_proj = update_npc_generic_logic(npc, self.players, self.agora_ms, dt)
            if new_proj: novos_projeteis.append(new_proj)

        self.projectiles.extend(novos_projeteis)
        
        toremove_proj = set()
        toremove_obs = set()
        toremove_npc = set()
        
        for proj in self.projectiles:
            update_projectile_physics(proj, living_targets, self.agora_ms, dt)
            dist_percorrida_sq = (proj['x'] - proj['pos_inicial_x'])**2 + (proj['y'] - proj['pos_inicial_y'])**2
            p_ref = proj 

            if dist_percorrida_sq > MAX_DISTANCIA_TIRO_SQ: toremove_proj.add(id(p_ref)); continue
            if not (0 <= proj['x'] <= s.MAP_WIDTH and 0 <= proj['y'] <= s.MAP_HEIGHT): toremove_proj.add(id(p_ref)); continue

            hit = False
            for obs in self.obstaculos:
                if id(obs) in toremove_obs: continue
                if (obs['x'] - proj['x'])**2 + (obs['y'] - proj['y'])**2 < (obs['raio'] + 5)**2:
                    obs['hp'] -= proj['dano']; hit = True
                    if obs['hp'] <= 0:
                        toremove_obs.add(id(obs))
                        owner = next((p for p in self.players.values() if p['nome'] == proj['owner_nome']), None)
                        if owner: server_ganhar_pontos(owner, obs.get('pontos_por_morte', 1))
                    break
            if hit: toremove_proj.add(id(p_ref)); continue

            if proj['tipo'].startswith('player') or proj['tipo'] == 'npc':
                for target in living_players:
                    if target['nome'] == proj['owner_nome']: continue
                    
                    if (target['x'] - proj['x'])**2 + (target['y'] - proj['y'])**2 < COLISAO_JOGADOR_PROJ_DIST_SQ:
                        if target.get('propulsor_ativo', False): hit = True; break 

                        dano = proj['dano']
                        reducao = min(target['nivel_escudo'] * REDUCAO_DANO_POR_NIVEL, 75) / 100.0
                        old_hp = target['hp']
                        target['hp'] -= dano * (1.0 - reducao)
                        target['ultimo_hit_tempo'] = self.agora_ms
                        target['esta_regenerando'] = False
                        
                        if old_hp > 0 and target['hp'] <= 0:
                            if proj['tipo'].startswith('player'):
                                killer_name = proj['owner_nome']
                                killer = next((p for p in self.players.values() if p['nome'] == killer_name), None)
                                if killer:
                                    recompensa = int(target['pontos'] * 0.8) 
                                    if recompensa > 0: server_ganhar_pontos(killer, recompensa)

                        if target['nivel_escudo'] >= s.MAX_NIVEL_ESCUDO:
                            dx = proj['x'] - target['x']; dy = proj['y'] - target['y']; angle = math.atan2(dy, dx)
                            target['shield_hit'] = {'time': self.agora_ms, 'angle': angle}
                        hit = True; break
            if hit: toremove_proj.add(id(p_ref)); continue

            if proj['tipo'].startswith('player'):
                for npc in self.npcs:
                    if npc.get('hp') <= 0: continue
                    raio_npc = npc.get('tamanho', 30) / 2
                    if (npc['x'] - proj['x'])**2 + (npc['y'] - proj['y'])**2 < (raio_npc + 5)**2:
                        npc['hp'] -= proj['dano']; npc['ultimo_hit_tempo'] = self.agora_ms
                        npc['ia_alvo_retaliacao'] = proj['owner_nome']
                        hit = True
                        if npc['hp'] <= 0:
                            toremove_npc.add(id(npc))
                            owner = next((p for p in self.players.values() if p['nome'] == proj['owner_nome']), None)
                            if owner: server_ganhar_pontos(owner, npc.get('pontos_por_morte', 5))
                        break
            if hit: toremove_proj.add(id(p_ref))

        if toremove_proj: self.projectiles = [p for p in self.projectiles if id(p) not in toremove_proj]
        if toremove_obs: self.obstaculos = [o for o in self.obstaculos if id(o) not in toremove_obs]
        if toremove_npc: self.npcs = [n for n in self.npcs if id(n) not in toremove_npc]

    def get_state_json(self):
        players_list = []
        for p in self.players.values():
            if p['hp'] > 0 or p.get('is_spectator', False):
                p_data = {
                    "id": p['nome'], "x": round(p['x'], 1), "y": round(p['y'], 1), "angle": int(p['angulo']),
                    "hp": round(p['hp'], 1), "max_hp": p['max_hp'], "score": p['pontos'],
                    "regen": p.get('esta_regenerando', False), "pts_up": p['pontos_upgrade_disponiveis'],
                    "nv_motor": p['nivel_motor'], "nv_dano": p['nivel_dano'], "nv_hp": p['nivel_max_vida'],
                    "nv_escudo": p['nivel_escudo'], "nv_aux": p['nivel_aux'], "is_bot": p.get('is_bot', False),
                    "propulsor_ativo": p.get('propulsor_ativo', False),
                    "is_spectator": p.get('is_spectator', False)
                }
                if p.get('shield_hit') and self.agora_ms - p['shield_hit']['time'] < 200:
                    p_data['shield_hit'] = True; p_data['shield_angle'] = p['shield_hit']['angle']
                if p['alvo_mouse']: p_data["tx"] = int(p['alvo_mouse'][0]); p_data["ty"] = int(p['alvo_mouse'][1])
                players_list.append(p_data)
        
        proj_list = [{"id": pr['id'], "x": round(pr['x'], 1), "y": round(pr['y'], 1), "type": pr['tipo']} for pr in self.projectiles]
        npcs_list = []
        for n in self.npcs:
            if n.get('hp') > 0: npcs_list.append({"id": n['id'], "x": round(n['x'], 1), "y": round(n['y'], 1), "angle": int(n.get('angulo', 0)), "type": n['tipo'], "size": n.get('tamanho', 30), "hp": round(n['hp']), "max_hp": n.get('max_hp', 1)})
        for o in self.obstaculos:
            npcs_list.append({"id": o['id'], "x": round(o['x'], 1), "y": round(o['y'], 1), "type": "obstaculo", "size": o['raio'], "hp": o['hp'], "max_hp": o['max_hp']})

        return { "type": "STATE", "timestamp": self.agora_ms, "players": players_list, "projectiles": proj_list, "npcs": npcs_list }

class PvpRoom(GameRoom):
    def __init__(self, room_id):
        super().__init__(room_id, "PVP", MAX_PLAYERS_PVP)
        self.state = "WAITING"
        self.timer_end = 0
        self.winner = ""

    def is_full(self):
        active_fighters = sum(1 for p in self.players.values() if not p.get('is_spectator', False))
        return active_fighters >= self.max_players

    def update(self, dt_multiplier=1.0):
        self.agora_ms = int(time.time() * 1000)
        active_fighters_count = sum(1 for p in self.players.values() if not p.get('is_spectator', False))
        
        if self.state == "WAITING":
            if active_fighters_count >= 4:
                self.state = "LOBBY_COUNTDOWN"
                self.timer_end = self.agora_ms + (pvp_s.PVP_LOBBY_COUNTDOWN_SEGUNDOS * 1000)
        elif self.state == "LOBBY_COUNTDOWN":
            if active_fighters_count < 4: self.state = "WAITING"
            elif self.agora_ms >= self.timer_end: self.start_pre_match()
        elif self.state == "PRE_MATCH":
            if self.agora_ms >= self.timer_end:
                self.state = "PLAYING"
                self.timer_end = self.agora_ms + (pvp_s.PVP_PARTIDA_DURACAO_SEGUNDOS * 1000)
                for p in self.players.values(): 
                    if not p.get('is_spectator'): p['is_pre_match'] = False
        elif self.state == "PLAYING":
            survivors = [p for p in self.players.values() if p['hp'] > 0 and not p.get('is_spectator')]
            if len(survivors) <= 1:
                self.winner = survivors[0]['nome'] if survivors else "Empate"
                self.state = "GAME_OVER"; self.timer_end = self.agora_ms + 10000
            elif self.agora_ms >= self.timer_end:
                survivors.sort(key=lambda p: p['hp'], reverse=True)
                self.winner = survivors[0]['nome'] if survivors else "Empate"
                self.state = "GAME_OVER"; self.timer_end = self.agora_ms + 10000
        elif self.state == "GAME_OVER":
            if self.agora_ms >= self.timer_end: self.reset_room()

        self._update_pvp_physics(dt_multiplier)

    def start_pre_match(self):
        self.state = "PRE_MATCH"
        self.timer_end = self.agora_ms + 5000 
        players_list = [p for p in self.players.values() if not p.get('is_spectator')]
        for i, p in enumerate(players_list):
            if i < len(pvp_s.SPAWN_POSICOES):
                spawn = pvp_s.SPAWN_POSICOES[i]
                p['x'], p['y'] = spawn.x, spawn.y
                p['hp'] = p['max_hp']; p['is_pre_match'] = True
                p['alvo_mouse'] = None; p['alvo_lock'] = None

    def reset_room(self):
        self.state = "WAITING"; self.projectiles = []; self.winner = ""
        for p in self.players.values():
            if p.get('is_spectator'): continue
            p['x'], p['y'] = pvp_s.SPAWN_LOBBY.x, pvp_s.SPAWN_LOBBY.y
            p['hp'] = p['max_hp']; p['is_pre_match'] = False
            p['pontos'] = 0; p['nivel_motor'] = 1; p['nivel_dano'] = 1; p['nivel_escudo'] = 0
            p['nivel_max_vida'] = 1; p['nivel_aux'] = 0
            p['pontos_upgrade_disponiveis'] = 10; p['total_upgrades_feitos'] = 0
            p['max_hp'] = float(s.VIDA_POR_NIVEL[1]); p['hp'] = p['max_hp']
            p['propulsor_ativo'] = False; p['fim_propulsor'] = 0; p['cooldown_propulsor'] = 0

    def _update_pvp_physics(self, dt):
        damage_enabled = (self.state == "PLAYING")
        move_enabled = (self.state != "PRE_MATCH") 
        living_players = [p for p in self.players.values() if p['hp'] > 0 and not p.get('is_spectator')]
        
        for p in living_players:
            if not move_enabled: p['teclas'] = {'w':False,'a':False,'s':False,'d':False,'space':False}; p['alvo_mouse'] = None
            new_proj = update_player_logic(p, living_players, self.agora_ms, pvp_s.MAP_WIDTH, pvp_s.MAP_HEIGHT, dt)
            if new_proj: self.projectiles.append(new_proj)
            if damage_enabled:
                aux_projs = process_auxiliaries_logic(p, living_players, self.agora_ms)
                if aux_projs: self.projectiles.extend(aux_projs)

        toremove_proj = set()
        for proj in self.projectiles:
            update_projectile_physics(proj, living_players, self.agora_ms, dt)
            p_ref = proj 
            if not (0 <= proj['x'] <= pvp_s.MAP_WIDTH and 0 <= proj['y'] <= pvp_s.MAP_HEIGHT): toremove_proj.add(id(p_ref)); continue
            if damage_enabled:
                for target in living_players:
                    if target['nome'] == proj['owner_nome']: continue
                    if (target['x'] - proj['x'])**2 + (target['y'] - proj['y'])**2 < COLISAO_JOGADOR_PROJ_DIST_SQ:
                        if target.get('propulsor_ativo', False): toremove_proj.add(id(p_ref)); break
                        dano = proj['dano']; reducao = min(target['nivel_escudo'] * REDUCAO_DANO_POR_NIVEL, 75) / 100.0
                        old_hp = target['hp']; target['hp'] -= dano * (1.0 - reducao); target['ultimo_hit_tempo'] = self.agora_ms
                        if old_hp > 0 and target['hp'] <= 0:
                            if proj['tipo'].startswith('player'):
                                killer_name = proj['owner_nome']
                                killer = next((p for p in self.players.values() if p['nome'] == killer_name), None)
                                if killer: recompensa = int(target['pontos'] * 0.8); server_ganhar_pontos(killer, recompensa) if recompensa > 0 else None
                        if target['nivel_escudo'] >= s.MAX_NIVEL_ESCUDO: 
                            dx = proj['x'] - target['x']; dy = proj['y'] - target['y']; angle = math.atan2(dy, dx)
                            target['shield_hit'] = {'time': self.agora_ms, 'angle': angle}
                        toremove_proj.add(id(p_ref)); break
        
        if toremove_proj: self.projectiles = [p for p in self.projectiles if id(p) not in toremove_proj]

    def get_state_json(self):
        players_list = []
        for p in self.players.values():
            if p['hp'] > 0 or p.get('is_spectator', False):
                p_data = {
                    "id": p['nome'], "x": round(p['x'], 1), "y": round(p['y'], 1), "angle": int(p['angulo']),
                    "hp": round(p['hp'], 1), "max_hp": p['max_hp'], "score": p['pontos'],
                    "is_bot": False, "pts_up": p['pontos_upgrade_disponiveis'], "nv_motor": p['nivel_motor'], "nv_dano": p['nivel_dano'], 
                    "nv_hp": p['nivel_max_vida'], "nv_escudo": p['nivel_escudo'], "nv_aux": p['nivel_aux'],
                    "propulsor_ativo": p.get('propulsor_ativo', False), "is_spectator": p.get('is_spectator', False)
                }
                if p.get('shield_hit') and self.agora_ms - p['shield_hit']['time'] < 200:
                    p_data['shield_hit'] = True; p_data['shield_angle'] = p['shield_hit']['angle']
                players_list.append(p_data)
        
        proj_list = [{"id": pr['id'], "x": round(pr['x'], 1), "y": round(pr['y'], 1), "type": pr['tipo']} for pr in self.projectiles]
        active_fighters_count = sum(1 for p in self.players.values() if not p.get('is_spectator', False))
        pvp_data = {
            "state": self.state, "timer_end": self.timer_end - self.agora_ms, "winner": self.winner,
            "players_count": active_fighters_count, "max_players": self.max_players
        }
        return { "type": "PVP_STATE", "timestamp": self.agora_ms, "players": players_list, "projectiles": proj_list, "pvp": pvp_data }

ROOMS = {}
for i in range(QTD_SALAS_PVE): rid = f"PVE_{i+1}"; ROOMS[rid] = PveRoom(rid)
for i in range(QTD_SALAS_PVP): rid = f"PVP_{i+1}"; ROOMS[rid] = PvpRoom(rid)

def find_available_room(mode):
    for room in ROOMS.values():
        if room.game_mode == mode:
            if mode == "PVP" and room.state not in ["WAITING", "LOBBY_COUNTDOWN"]: continue
            if not room.is_full(): return room
    return None

def find_spectator_room(mode):
    for room in ROOMS.values():
        if room.game_mode == mode and room.has_spectator_slot(): return room
    return None

async def game_loop():
    print(f"Servidor Iniciado. PVE: {QTD_SALAS_PVE}, PVP: {QTD_SALAS_PVP}. Tick: {TICK_RATE}")
    dt_multiplier = REFERENCE_FPS / TICK_RATE
    while True:
        st = time.time()
        try:
            for room in ROOMS.values():
                room.update(dt_multiplier)
                state = room.get_state_json()
                await room.broadcast(state)
        except Exception as e:
            print(f"[CRITICAL ERROR IN GAME LOOP]: {e}")
            traceback.print_exc()
        elapsed = time.time() - st
        if elapsed > 0.1: print(f"[LAG WARNING] Tick took {elapsed:.3f}s")
        await asyncio.sleep(max(0, (1.0 / TICK_RATE) - elapsed))

async def handler(websocket):
    current_room = None
    is_spectator_on_join = False
    try:
        msg = await websocket.recv()
        data = json.loads(msg)
        if data.get("type") != "LOGIN": await websocket.close(); return
        player_name = data.get("name", "Player")
        mode = data.get("mode", "PVE")
        current_room = find_available_room(mode)
        if not current_room and mode == "PVP":
            current_room = find_spectator_room(mode)
            if current_room: is_spectator_on_join = True
        if not current_room: await websocket.close(1008, "Servidor lotado, tente mais tarde..."); return

        spawn_x, spawn_y = 0, 0; upgrade_pts = 0; map_w, map_h = 0, 0
        if mode == "PVP": spawn_x, spawn_y = pvp_s.SPAWN_LOBBY.x, pvp_s.SPAWN_LOBBY.y; upgrade_pts = 10; map_w, map_h = pvp_s.MAP_WIDTH, pvp_s.MAP_HEIGHT
        else: spawn_x, spawn_y = server_calcular_posicao_spawn([], s.MAP_WIDTH, s.MAP_HEIGHT); upgrade_pts = 0; map_w, map_h = s.MAP_WIDTH, s.MAP_HEIGHT

        hp_init = float(s.VIDA_POR_NIVEL[1])
        p_state = {
            'nome': f"{player_name}_{int(time.time())}", 'x': spawn_x, 'y': spawn_y, 'angulo': 0,
            'hp': hp_init, 'max_hp': hp_init, 'teclas': {'w':False,'a':False,'s':False,'d':False,'space':False},
            'alvo_mouse': None, 'alvo_lock': None, 'pontos': 0, 'cooldown_tiro': COOLDOWN_TIRO, 'ultimo_tiro_tempo': 0,
            'nivel_motor': 1, 'nivel_dano': 1, 'nivel_max_vida': 1, 'nivel_escudo': 0,
            'pontos_upgrade_disponiveis': upgrade_pts, 'total_upgrades_feitos': 0,
            'nivel_aux': 0, 'aux_cooldowns': [0]*4, 'is_bot': False, 'esta_regenerando': False,
            'is_pvp': (mode == "PVP"),
            '_pontos_acumulados_para_upgrade': 0, '_limiar_pontos_atual': PONTOS_LIMIARES_PARA_UPGRADE[0], '_indice_limiar': 0,
            'propulsor_ativo': False, 'fim_propulsor': 0, 'cooldown_propulsor': 0,
            'is_spectator': is_spectator_on_join
        }
        if is_spectator_on_join: p_state['hp'] = 0; p_state['x'] = map_w / 2; p_state['y'] = map_h / 2

        current_room.clients.add(websocket)
        current_room.players[websocket] = p_state
        await websocket.send(json.dumps({ "type": "WELCOME", "id": p_state['nome'], "x": spawn_x, "y": spawn_y, "mode": mode, "map_width": map_w, "map_height": map_h }))

        async for message in websocket:
            try:
                cmd = json.loads(message)
                if p_state.get('is_spectator'): continue
                if cmd["type"] == "INPUT":
                    p_state['teclas']['w'] = cmd.get('w', False); p_state['teclas']['a'] = cmd.get('a', False)
                    p_state['teclas']['s'] = cmd.get('s', False); p_state['teclas']['d'] = cmd.get('d', False)
                    p_state['teclas']['space'] = cmd.get('space', False)
                    if 'mouse_x' in cmd: p_state['alvo_mouse'] = (cmd['mouse_x'], cmd['mouse_y'])
                elif cmd["type"] == "ATIVAR_PROPULSOR":
                    agora = int(time.time() * 1000)
                    if agora > p_state['cooldown_propulsor']:
                        p_state['propulsor_ativo'] = True
                        p_state['fim_propulsor'] = agora + s.DURACAO_PROPULSOR_IMUNE
                        p_state['cooldown_propulsor'] = agora + s.COOLDOWN_PROPULSOR
                        for other_p in current_room.players.values():
                            if other_p.get('alvo_lock') == p_state['nome']: other_p['alvo_lock'] = None
                        for npc in current_room.npcs:
                            if npc.get('ia_alvo_id') == p_state['nome']: npc['ia_alvo_id'] = None
                elif cmd["type"] == "UPGRADE": server_comprar_upgrade(p_state, cmd.get("item"))
                elif cmd["type"] == "TARGET":
                    click_x, click_y = cmd.get('x'), cmd.get('y')
                    melhor_dist = float('inf'); melhor_id = None
                    candidatos = []
                    candidatos.extend(current_room.npcs); candidatos.extend(current_room.obstaculos)
                    for p in current_room.players.values():
                        if p['nome'] != p_state['nome'] and not p.get('is_spectator'): candidatos.append(p)
                    for alvo in candidatos:
                        if alvo.get('hp', 0) <= 0: continue
                        dist_sq = (alvo['x'] - click_x)**2 + (alvo['y'] - click_y)**2
                        if dist_sq < TARGET_CLICK_SIZE_SQ and dist_sq < melhor_dist:
                            melhor_dist = dist_sq; melhor_id = alvo.get('id', alvo.get('nome'))
                    alvo_obj = next((p for p in current_room.players.values() if p['nome'] == melhor_id), None)
                    if alvo_obj and alvo_obj.get('propulsor_ativo', False): p_state['alvo_lock'] = None 
                    else: p_state['alvo_lock'] = melhor_id
                elif cmd["type"] == "TOGGLE_REGEN":
                    if not p_state.get('esta_regenerando') and p_state['hp'] < p_state['max_hp']: p_state['esta_regenerando'] = True
                    else: p_state['esta_regenerando'] = False
                elif cmd["type"] == "ENTER_SPECTATOR": p_state['hp'] = 0; p_state['esta_regenerando'] = False
                elif cmd["type"] == "RESPAWN" and mode == "PVE":
                    if p_state['hp'] <= 0:
                        spawn_x, spawn_y = server_calcular_posicao_spawn([], s.MAP_WIDTH, s.MAP_HEIGHT)
                        p_state['x'] = spawn_x; p_state['y'] = spawn_y
                        hp_init = float(s.VIDA_POR_NIVEL[1])
                        p_state['nivel_max_vida'] = 1; p_state['max_hp'] = hp_init; p_state['hp'] = hp_init
                        p_state['pontos'] = 0; p_state['pontos_upgrade_disponiveis'] = 0; p_state['total_upgrades_feitos'] = 0
                        p_state['nivel_motor'] = 1; p_state['nivel_dano'] = 1; p_state['nivel_escudo'] = 0; p_state['nivel_aux'] = 0
                        p_state['alvo_lock'] = None; p_state['alvo_mouse'] = None
                        p_state['esta_regenerando'] = False 
                        p_state['propulsor_ativo'] = False; p_state['fim_propulsor'] = 0; p_state['cooldown_propulsor'] = 0
            except: pass
    except: pass
    finally:
        if current_room: current_room.remove_player(websocket)

async def main():
    server = await websockets.serve(handler, "0.0.0.0", PORT, ping_interval=20, ping_timeout=60)
    print(f"Servidor WebSocket rodando na porta {PORT}...")
    await asyncio.gather(server.wait_closed(), game_loop())

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass