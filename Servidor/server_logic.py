# Servidor/server_logic.py
import random
import math
import time
import pygame
import settings as s
import multi.pvp_settings as pvp_s

# ==================================================================================
# 1. CONSTANTES E CONFIGURAÇÕES
# ==================================================================================

# Configurações de Salas
QTD_SALAS_PVE = 2
MAX_PLAYERS_PVE = 16
QTD_SALAS_PVP = 4
MAX_PLAYERS_PVP = pvp_s.MAX_JOGADORES_PVP

AOI_RADIUS_SQ = 3500**2 

# Constantes de Distância e Física
COLISAO_JOGADOR_PROJ_DIST_SQ = (15 + 5)**2
COLISAO_JOGADOR_NPC_DIST_SQ = (15 + 15)**2 
NPC_DETECTION_RANGE_SQ = (3000 ** 2)
MAX_DISTANCIA_TIRO_SQ = s.MAX_DISTANCIA_TIRO**2

# Timers
LOBBY_COUNTDOWN_MS = pvp_s.PVP_LOBBY_COUNTDOWN_SEGUNDOS * 1000
PARTIDA_COUNTDOWN_MS = pvp_s.PVP_PARTIDA_DURACAO_SEGUNDOS * 1000
PRE_MATCH_FREEZE_MS = 5000
RESTART_DELAY_MS = 10000 
SPAWN_PROTECTION_MS = 3000 

# Constantes Gerais
COOLDOWN_TIRO = 250 
OFFSET_PONTA_TIRO = 25 
VELOCIDADE_PERSEGUIDOR = 2.0 
DISTANCIA_PARAR_PERSEGUIDOR_SQ = 200**2 
SPAWN_DIST_MIN = s.SPAWN_DIST_MIN
COOLDOWN_TIRO_PERSEGUIDOR = 2000 
DISTANCIA_TIRO_PERSEGUIDOR_SQ = 500**2 
VELOCIDADE_PROJETIL_NPC = 7 
MAX_TARGET_LOCK_DISTANCE_SQ = s.MAX_TARGET_LOCK_DISTANCE**2 
TARGET_CLICK_SIZE_SQ = (s.TARGET_CLICK_SIZE / 2)**2 
REGEN_POR_TICK = s.REGEN_POR_TICK
REGEN_TICK_RATE_MS = s.REGEN_TICK_RATE
REDUCAO_DANO_POR_NIVEL = s.REDUCAO_DANO_POR_NIVEL

# Projéteis Especiais
VELOCIDADE_PROJETIL_TELE = 14    
DURACAO_PROJETIL_TELE_MS = 2000 
TURN_SPEED_TELE = 0.15          
VELOCIDADE_PROJ_LENTO = 9.0
DURACAO_PROJ_LENTO_MS = 5000
VELOCIDADE_PROJ_CONGELANTE = 8.0
DURACAO_PROJ_CONGELANTE_MS = 700
DURACAO_LENTIDAO_MS = 6000
DURACAO_CONGELAMENTO_MS = 2000

# Bosses, Minions e Auxiliares
COOLDOWN_SPAWN_MINION_CONGELANTE = 10000
MAX_MINIONS_CONGELANTE = 6
MAX_MINIONS_MOTHERSHIP = 8
COOLDOWN_TIRO_MINION_CONGELANTE = 600
HP_MINION_CONGELANTE = 10
PONTOS_MINION_CONGELANTE = 5
VELOCIDADE_MINION_CONGELANTE = 2.5 
MINION_CONGELANTE_LEASH_RANGE = 1500
MAX_AUXILIARES = 4 
CUSTOS_AUXILIARES = s.CUSTOS_AUXILIARES
AUX_POSICOES = [(-40, 20), (40, 20), (-50, -10), (50, -10)]
AUX_COOLDOWN_TIRO = 1000 
AUX_DISTANCIA_TIRO_SQ = 600**2 

# Upgrades
MAX_TOTAL_UPGRADES = s.MAX_TOTAL_UPGRADES
MAX_NIVEL_MOTOR = s.MAX_NIVEL_MOTOR
MAX_NIVEL_DANO = s.MAX_NIVEL_DANO
MAX_NIVEL_ESCUDO = s.MAX_NIVEL_ESCUDO
PONTOS_LIMIARES_PARA_UPGRADE = s.PONTOS_LIMIARES_PARA_UPGRADE[:]
PONTOS_SCORE_PARA_MUDAR_LIMIAR = s.PONTOS_SCORE_PARA_MUDAR_LIMIAR[:]
VIDA_POR_NIVEL = s.VIDA_POR_NIVEL

# ==================================================================================
# 2. FUNÇÕES AUXILIARES E LÓGICA DE JOGO
# ==================================================================================

def server_ganhar_pontos(player_state, quantidade):
    if quantidade <= 0: return
    player_state['pontos'] += quantidade 
    player_state['_pontos_acumulados_para_upgrade'] += quantidade
    while player_state['_pontos_acumulados_para_upgrade'] >= player_state['_limiar_pontos_atual']:
        player_state['pontos_upgrade_disponiveis'] += 1
        player_state['_pontos_acumulados_para_upgrade'] -= player_state['_limiar_pontos_atual'] 
        pontos_totais = player_state['pontos'] 
        if (player_state['_indice_limiar'] < len(PONTOS_SCORE_PARA_MUDAR_LIMIAR) and 
            pontos_totais >= PONTOS_SCORE_PARA_MUDAR_LIMIAR[player_state['_indice_limiar']]):
            player_state['_indice_limiar'] += 1
            if player_state['_indice_limiar'] < len(PONTOS_LIMIARES_PARA_UPGRADE):
                player_state['_limiar_pontos_atual'] = PONTOS_LIMIARES_PARA_UPGRADE[player_state['_indice_limiar']]

def server_comprar_upgrade(player_state, tipo_upgrade):
    is_pvp = player_state.get('is_pvp', False)
    limite_total = pvp_s.PONTOS_ATRIBUTOS_INICIAIS if is_pvp else MAX_TOTAL_UPGRADES
    if player_state['pontos_upgrade_disponiveis'] <= 0: return
    if player_state['total_upgrades_feitos'] >= limite_total: return
    custo = 1; comprou = False
    if tipo_upgrade == "motor" and player_state['nivel_motor'] < MAX_NIVEL_MOTOR:
        player_state['pontos_upgrade_disponiveis'] -= custo; player_state['total_upgrades_feitos'] += 1; player_state['nivel_motor'] += 1; comprou = True
    elif tipo_upgrade == "dano" and player_state['nivel_dano'] < MAX_NIVEL_DANO:
        player_state['pontos_upgrade_disponiveis'] -= custo; player_state['total_upgrades_feitos'] += 1; player_state['nivel_dano'] += 1; comprou = True
    elif tipo_upgrade == "auxiliar":
        num = player_state['nivel_aux']
        if num < MAX_AUXILIARES:
            c_aux = CUSTOS_AUXILIARES[num] 
            if player_state['pontos_upgrade_disponiveis'] >= c_aux:
                player_state['pontos_upgrade_disponiveis'] -= c_aux; player_state['total_upgrades_feitos'] += 1; player_state['nivel_aux'] += 1; comprou = True
    elif tipo_upgrade == "max_health" and player_state['nivel_max_vida'] < len(s.VIDA_POR_NIVEL) - 1:
        player_state['pontos_upgrade_disponiveis'] -= custo; player_state['total_upgrades_feitos'] += 1; player_state['nivel_max_vida'] += 1; player_state['max_hp'] = s.VIDA_POR_NIVEL[player_state['nivel_max_vida']]; player_state['hp'] += 1; comprou = True
    elif tipo_upgrade == "escudo" and player_state['nivel_escudo'] < MAX_NIVEL_ESCUDO:
        player_state['pontos_upgrade_disponiveis'] -= custo; player_state['total_upgrades_feitos'] += 1; player_state['nivel_escudo'] += 1; comprou = True

def server_calcular_posicao_spawn(pos_referencia_lista, map_width, map_height):
    for _ in range(20):
        x = random.uniform(100, map_width - 100); y = random.uniform(100, map_height - 100); longe = True
        if pos_referencia_lista: 
            for px, py in pos_referencia_lista:
                if (x - px)**2 + (y - py)**2 < 600**2: # Margem maior
                    longe = False; break
        if longe: return (float(x), float(y))
    return (float(random.uniform(100, map_width - 100)), float(random.uniform(100, map_height - 100)))

def _rotate_vector(x, y, angle_degrees):
    rad = math.radians(angle_degrees); cosa = math.cos(rad); sina = math.sin(rad)
    return x * cosa - y * sina, x * sina + y * cosa

def calc_hit_angle_rad(target_x, target_y, attacker_x, attacker_y):
    dx = attacker_x - target_x
    dy = attacker_y - target_y
    if dx == 0 and dy == 0: return 0
    return math.atan2(dy, dx)

def update_player_logic(player_state, lista_alvos_busca, agora_ms, map_width, map_height): 
    if agora_ms < player_state.get('tempo_fim_congelamento', 0): player_state['alvo_mouse'] = None; return None
    if player_state.get('is_pre_match', False): player_state['alvo_mouse'] = None; return None
    is_lento = agora_ms < player_state.get('tempo_fim_lentidao', 0)

    if player_state['alvo_lock']:
        alvo = next((e for e in lista_alvos_busca if e.get('id', e.get('nome')) == player_state['alvo_lock']), None)
        if alvo and alvo.get('hp', 0) > 0:
            vec_x = alvo['x'] - player_state['x']; vec_y = alvo['y'] - player_state['y']
            if vec_x**2 + vec_y**2 > MAX_TARGET_LOCK_DISTANCE_SQ: player_state['alvo_lock'] = None
            else: player_state['angulo'] = (-math.degrees(math.atan2(vec_y, vec_x)) - 90) % 360
        else: player_state['alvo_lock'] = None
    elif player_state['alvo_mouse']:
        vec_x = player_state['alvo_mouse'][0] - player_state['x']; vec_y = player_state['alvo_mouse'][1] - player_state['y']
        if vec_x**2 + vec_y**2 > 25: player_state['angulo'] = (-math.degrees(math.atan2(vec_y, vec_x)) - 90) % 360

    if not player_state['alvo_lock'] and not player_state['alvo_mouse']:
        if player_state['teclas']['a']: player_state['angulo'] = (player_state['angulo'] + 5) % 360
        if player_state['teclas']['d']: player_state['angulo'] = (player_state['angulo'] - 5) % 360

    vel = (4 + player_state['nivel_motor'] * 0.5) * (0.4 if is_lento else 1.0) + 1
    vx, vy = 0, 0
    rad = math.radians(player_state['angulo'])
    if player_state['teclas']['w']: vx += -math.sin(rad) * vel; vy += -math.cos(rad) * vel
    if player_state['teclas']['s']: vx -= -math.sin(rad) * vel; vy -= -math.cos(rad) * vel
    
    if player_state['alvo_mouse'] and not (player_state['teclas']['w'] or player_state['teclas']['s']):
        tx, ty = player_state['alvo_mouse']
        dx, dy = tx - player_state['x'], ty - player_state['y']
        dist = math.sqrt(dx**2 + dy**2)
        if dist > vel: vx, vy = (dx/dist)*vel, (dy/dist)*vel
        else: player_state['x'], player_state['y'] = tx, ty; player_state['alvo_mouse'] = None; vx, vy = 0, 0

    player_state['x'] = max(15, min(player_state['x'] + vx, map_width - 15))
    player_state['y'] = max(15, min(player_state['y'] + vy, map_height - 15))

    if (player_state['teclas']['space'] or player_state['alvo_lock']) and \
       (agora_ms - player_state['ultimo_tiro_tempo'] > player_state['cooldown_tiro']):
        
        player_state['ultimo_tiro_tempo'] = agora_ms
        rad = math.radians(player_state['angulo'])
        sx = player_state['x'] + (-math.sin(rad) * OFFSET_PONTA_TIRO)
        sy = player_state['y'] + (-math.cos(rad) * OFFSET_PONTA_TIRO)
        
        tipo_base = 'player_pvp' if player_state.get('is_pvp') else 'player_pve'
        if player_state['nivel_dano'] >= s.MAX_NIVEL_DANO: tipo_base += '_max' 

        proj = {
            'id': f"{player_state['nome']}_{agora_ms}", 'owner_nome': player_state['nome'],
            'x': sx, 'y': sy, 'pos_inicial_x': sx, 'pos_inicial_y': sy,
            'dano': s.DANO_POR_NIVEL[player_state['nivel_dano']],
            'tipo': tipo_base, 
            'timestamp_criacao': agora_ms
        }
        if player_state['alvo_lock']:
            proj.update({'tipo_proj': 'teleguiado', 'velocidade': VELOCIDADE_PROJETIL_TELE, 
                         'alvo_id': player_state['alvo_lock'], 
                         'vel_x': -math.sin(rad)*VELOCIDADE_PROJETIL_TELE, 'vel_y': -math.cos(rad)*VELOCIDADE_PROJETIL_TELE})
        else:
            proj.update({'tipo_proj': 'normal', 'velocidade': 25, 
                         'vel_x': -math.sin(rad)*25, 'vel_y': -math.cos(rad)*25})
        return proj
    return None

# ==================================================================================
# LÓGICA DE PROJÉTEIS
# ==================================================================================
def update_projectile_physics(proj, all_targets, agora_ms):
    # Move linearmente primeiro
    proj['x'] += proj.get('vel_x', 0)
    proj['y'] += proj.get('vel_y', 0)

    # Lógica de Homing
    if proj.get('tipo_proj') == 'teleguiado' and proj.get('alvo_id'):
        target = next((t for t in all_targets if t.get('id', t.get('nome')) == proj['alvo_id']), None)
        
        if target and target.get('hp', 0) > 0:
            curr_pos = pygame.math.Vector2(proj['x'], proj['y'])
            target_pos = pygame.math.Vector2(target['x'], target['y'])
            
            desired_vec = target_pos - curr_pos
            dist = desired_vec.length()
            
            if dist < 50:
                 proj['tipo_proj'] = 'normal'
                 return

            curr_vel = pygame.math.Vector2(proj['vel_x'], proj['vel_y'])
            
            if curr_vel.length() > 0 and dist > 0:
                 if curr_vel.normalize().dot(desired_vec.normalize()) < -0.2: 
                     proj['tipo_proj'] = 'normal'
                     return

            if dist > 0:
                desired_dir = desired_vec.normalize()
                if curr_vel.length() == 0: curr_vel = desired_dir * proj['velocidade']
                STEER_FACTOR = 0.20 
                new_dir = curr_vel.normalize().lerp(desired_dir, STEER_FACTOR)
                if new_dir.length() > 0: new_dir = new_dir.normalize()
                new_vel = new_dir * proj['velocidade']
                proj['vel_x'] = new_vel.x
                proj['vel_y'] = new_vel.y
        else:
            proj['tipo_proj'] = 'normal'

# ==================================================================================
# LÓGICA DE IA DOS INIMIGOS
# ==================================================================================
def update_npc_generic_logic(npc, players_dict, agora_ms):
    if npc.get('hp', 0) <= 0: return None
    players_pos_lista = [(p['x'], p['y']) for p in players_dict.values() if p['hp'] > 0]
    if not players_pos_lista: return None 
    alvo_pos = None; dist_min_sq = float('inf')
    for p_pos in players_pos_lista:
        dist_sq = (npc['x'] - p_pos[0])**2 + (npc['y'] - p_pos[1])**2
        if dist_sq > NPC_DETECTION_RANGE_SQ: continue
        if dist_sq < dist_min_sq: dist_min_sq = dist_sq; alvo_pos = p_pos 
    if not alvo_pos: return None
    vec_x = alvo_pos[0] - npc['x']; vec_y = alvo_pos[1] - npc['y']
    dist = math.sqrt(dist_min_sq)
    velocidade = VELOCIDADE_PERSEGUIDOR 
    if npc['tipo'] == 'rapido': velocidade = 4.0 
    elif npc['tipo'] == 'bomba': velocidade = 3.0 
    elif npc['tipo'] == 'tiro_rapido': velocidade = 1.5
    elif npc['tipo'] == 'atordoador': velocidade = 1.0
    if dist_min_sq > DISTANCIA_PARAR_PERSEGUIDOR_SQ or npc['tipo'] == 'bomba': 
        if dist > 0:
            dir_x = vec_x / dist; dir_y = vec_y / dist
            npc['x'] += dir_x * velocidade; npc['y'] += dir_y * velocidade
    radianos = math.atan2(vec_y, vec_x)
    npc['angulo'] = -math.degrees(radianos) - 90
    npc['angulo'] %= 360
    if npc['tipo'] in ['bomba']: return None 
    if dist_min_sq < DISTANCIA_TIRO_PERSEGUIDOR_SQ: 
        if agora_ms - npc['ultimo_tiro_tempo'] > npc['cooldown_tiro']:
            npc['ultimo_tiro_tempo'] = agora_ms
            dir_x = vec_x / dist; dir_y = vec_y / dist
            tipo_proj_npc = 'normal'; velocidade_proj = VELOCIDADE_PROJETIL_NPC; alvo_id_proj = None 
            if npc['tipo'] == 'tiro_rapido': velocidade_proj = 22 
            elif npc['tipo'] == 'rapido': velocidade_proj = 12 
            elif npc['tipo'] == 'atordoador':
                tipo_proj_npc = 'teleguiado_lento'; velocidade_proj = VELOCIDADE_PROJ_LENTO
                dist_min_sq_alvo = float('inf')
                for p_state in players_dict.values():
                    if p_state['hp'] <= 0: continue
                    p_dist_sq = (npc['x'] - p_state['x'])**2 + (npc['y'] - p_state['y'])**2
                    if p_dist_sq < dist_min_sq_alvo: dist_min_sq_alvo = p_dist_sq; alvo_id_proj = p_state['nome']
            vel_x = 0; vel_y = 0
            if tipo_proj_npc == 'normal':
                vel_x = math.cos(radianos) * velocidade_proj
                vel_y = math.sin(radianos) * velocidade_proj
            else: 
                if not alvo_id_proj: return None 
                vel_x = dir_x * velocidade_proj; vel_y = dir_y * velocidade_proj
            return {'id': f"{npc['id']}_{agora_ms}", 'owner_nome': npc['id'], 'x': npc['x'], 'y': npc['y'], 'pos_inicial_x': npc['x'], 'pos_inicial_y': npc['y'], 'angulo_rad': radianos, 'velocidade': velocidade_proj, 'dano': 1, 'tipo': 'npc', 'tipo_proj': tipo_proj_npc, 'alvo_id': alvo_id_proj, 'timestamp_criacao': agora_ms, 'vel_x': vel_x, 'vel_y': vel_y}
    return None

def update_mothership_logic(npc, players_dict, agora_ms, room_ref):
    if npc.get('hp', 0) <= 0: return None
    
    # CORREÇÃO IA: Usar 'ultimo_hit_tempo' (que é atualizado no server_ws.py ao levar dano)
    tempo_ultimo_dano = npc.get('ultimo_hit_tempo', 0)
    
    if (agora_ms - tempo_ultimo_dano < 3000) and npc.get('ia_alvo_retaliacao') is None:
        alvo_prox = None; dist_min = float('inf')
        for p in players_dict.values():
             if p['hp'] <= 0: continue
             d = (p['x']-npc['x'])**2 + (p['y']-npc['y'])**2
             if d < dist_min: dist_min = d; alvo_prox = p
        if alvo_prox: npc['ia_alvo_retaliacao'] = alvo_prox['nome']; npc['ia_estado'] = 'RETALIANDO'
        
    if npc.get('ia_estado') == 'VAGANDO':
        cx, cy = s.MAP_WIDTH/2, s.MAP_HEIGHT/2
        dx, dy = cx - npc['x'], cy - npc['y']
        dist = math.sqrt(dx**2 + dy**2)
        if dist > 50: npc['x'] += (dx/dist) * 0.5; npc['y'] += (dy/dist) * 0.5
        
    elif npc.get('ia_estado') == 'RETALIANDO':
        t_id = npc.get('ia_alvo_retaliacao')
        target = next((p for p in players_dict.values() if p['nome'] == t_id and p['hp'] > 0), None)
        
        if not target: 
            npc['ia_estado'] = 'VAGANDO'; npc['ia_alvo_retaliacao'] = None
        else:
            # Verifica minions vivos deste dono
            minions_vivos = [m for m in room_ref.npcs if m['tipo'] == 'minion_mothership' and m.get('owner_id') == npc['id']]
            
            # Se não tem minions, spawna o enxame
            if len(minions_vivos) == 0:
                 for i in range(8): # MAX_MINIONS_MOTHERSHIP
                     m = server_spawnar_minion_mothership(npc, t_id, i, 8, room_ref.next_npc_id)
                     room_ref.npcs.append(m); room_ref.next_npc_id += 1
            
            # Persegue o alvo lentamente
            dx, dy = npc['x'] - target['x'], npc['y'] - target['y']
            dist = math.sqrt(dx**2 + dy**2) + 0.1
            if dist < 800: npc['x'] += (dx/dist) * 1.0; npc['y'] += (dy/dist) * 1.0
    return None

def update_boss_congelante_logic(npc, players_dict, agora_ms, room_ref):
    if npc.get('hp', 0) <= 0: return None
    
    target = None; dist_min = float('inf')
    for p in players_dict.values():
        if p['hp'] <= 0: continue
        d = (p['x']-npc['x'])**2 + (p['y']-npc['y'])**2
        if d < dist_min: dist_min = d; target = p
    if not target: return None
    
    # Wander Logic
    if not npc.get('ia_wander_target') or (npc['x']-npc['ia_wander_target'][0])**2 + (npc['y']-npc['ia_wander_target'][1])**2 < 100**2:
        npc['ia_wander_target'] = (random.randint(100, s.MAP_WIDTH-100), random.randint(100, s.MAP_HEIGHT-100))
    wx, wy = npc['ia_wander_target']
    dx, dy = wx - npc['x'], wy - npc['y']
    dist = math.sqrt(dx**2 + dy**2)
    if dist > 5: npc['x'] += (dx/dist) * 1.0; npc['y'] += (dy/dist) * 1.0
    
    # Spawn Logic (CORRIGIDO: Usar ultimo_hit_tempo)
    tempo_ultimo_dano = npc.get('ultimo_hit_tempo', 0)
    
    if (agora_ms - tempo_ultimo_dano < 3000) and (agora_ms - npc.get('ia_ultimo_spawn_minion', 0) > 10000): # COOLDOWN_SPAWN
        minions = [m for m in room_ref.npcs if m['tipo'] == 'minion_congelante' and m.get('owner_id') == npc['id']]
        if len(minions) < 6: # MAX_MINIONS
            npc['ia_ultimo_spawn_minion'] = agora_ms
            m = server_spawnar_minion_congelante(npc, target['nome'], len(minions), 6, room_ref.next_npc_id)
            room_ref.npcs.append(m); room_ref.next_npc_id += 1
            
    # Tiro Congelante
    if agora_ms - npc.get('ultimo_tiro_tempo', 0) > s.COOLDOWN_TIRO_CONGELANTE:
        npc['ultimo_tiro_tempo'] = agora_ms
        tx, ty = target['x'], target['y']
        vx, vy = tx - npc['x'], ty - npc['y']
        d_t = math.sqrt(vx**2 + vy**2) + 0.1
        vel_x = (vx/d_t) * 8.0 # VELOCIDADE_PROJ_CONGELANTE
        vel_y = (vy/d_t) * 8.0
        return {'id': f"{npc['id']}_{agora_ms}", 'owner_nome': npc['id'], 'x': npc['x'], 'y': npc['y'], 'pos_inicial_x': npc['x'], 'pos_inicial_y': npc['y'], 'dano': 1, 'tipo': 'npc', 'tipo_proj': 'congelante', 'velocidade': 8.0, 'vel_x': vel_x, 'vel_y': vel_y, 'alvo_id': target['nome'], 'timestamp_criacao': agora_ms}
    return None

def update_minion_logic(npc, players_dict, agora_ms, room_ref):
    if npc.get('hp', 0) <= 0: return None
    owner = next((n for n in room_ref.npcs if n['id'] == npc.get('owner_id')), None)
    if not owner or owner['hp'] <= 0: npc['hp'] = 0; return None
    target = None
    if owner['tipo'] == 'mothership' and owner.get('ia_alvo_retaliacao'):
         target = next((p for p in players_dict.values() if p['nome'] == owner['ia_alvo_retaliacao']), None)
    elif npc.get('ia_alvo_id'):
         target = next((p for p in players_dict.values() if p['nome'] == npc['ia_alvo_id']), None)
    if not target or target['hp'] <= 0:
         dist_min = float('inf')
         for p in players_dict.values():
             if p['hp'] <= 0: continue
             d = (p['x']-npc['x'])**2 + (p['y']-npc['y'])**2
             if d < dist_min: dist_min = d; target = p
    npc['ia_angulo_orbita'] = (npc.get('ia_angulo_orbita', 0) + npc.get('ia_vel_orbita', 1)) % 360
    rad = math.radians(npc['ia_angulo_orbita'])
    raio = npc.get('ia_raio_orbita', 60)
    dest_x = owner['x'] + math.cos(rad) * raio
    dest_y = owner['y'] + math.sin(rad) * raio
    if target and npc['tipo'] == 'minion_congelante':
        d_owner_target = (owner['x']-target['x'])**2 + (owner['y']-target['y'])**2
        if d_owner_target < MINION_CONGELANTE_LEASH_RANGE**2:
            d_to_target_sq = (target['x']-npc['x'])**2 + (target['y']-npc['y'])**2
            if d_to_target_sq > 150**2: dest_x, dest_y = target['x'], target['y'] 
            else: dest_x, dest_y = npc['x'], npc['y']
    npc['x'] += (dest_x - npc['x']) * 0.1
    npc['y'] += (dest_y - npc['y']) * 0.1
    if target and agora_ms - npc.get('ultimo_tiro_tempo', 0) > npc['cooldown_tiro']:
         d_target = (target['x']-npc['x'])**2 + (target['y']-npc['y'])**2
         if d_target < 400**2:
             npc['ultimo_tiro_tempo'] = agora_ms
             dx, dy = target['x'] - npc['x'], target['y'] - npc['y']
             dist = math.sqrt(dx**2 + dy**2) + 0.1
             rad_tiro = math.atan2(dy, dx)
             vel_x = (dx/dist) * VELOCIDADE_PROJETIL_NPC
             vel_y = (dy/dist) * VELOCIDADE_PROJETIL_NPC
             return {'id': f"{npc['id']}_{agora_ms}", 'owner_nome': npc['id'], 'x': npc['x'], 'y': npc['y'], 'pos_inicial_x': npc['x'], 'pos_inicial_y': npc['y'], 'dano': 1, 'tipo': 'npc', 'tipo_proj': 'normal', 'velocidade': VELOCIDADE_PROJETIL_NPC, 'vel_x': vel_x, 'vel_y': vel_y, 'angulo_rad': rad_tiro}
    return None

def server_spawnar_inimigo_aleatorio(x, y, npc_id):
    chance = random.random(); tipo = "perseguidor"; hp = 3; max_hp = 3; tamanho = 30; cooldown_tiro = COOLDOWN_TIRO_PERSEGUIDOR; pontos = 5
    if chance < 0.05: tipo = "bomba"; hp, max_hp = 1, 1; tamanho = 25; cooldown_tiro = 999999; pontos = 3
    elif chance < 0.10: tipo = "tiro_rapido"; hp, max_hp = 10, 10; tamanho = 30; cooldown_tiro = 1500; pontos = 20
    elif chance < 0.15: tipo = "atordoador"; hp, max_hp = 5, 5; tamanho = 30; cooldown_tiro = 5000; pontos = 25
    elif chance < 0.35: tipo = "atirador_rapido"; hp, max_hp = 1, 1; tamanho = 30; cooldown_tiro = 500; pontos = 10
    elif chance < 0.55: tipo = "rapido"; hp, max_hp = 5, 5; tamanho = 30; cooldown_tiro = 800; pontos = 9
    return {'id': npc_id, 'tipo': tipo, 'x': float(x), 'y': float(y), 'angulo': 0.0, 'hp': hp, 'max_hp': max_hp, 'tamanho': tamanho, 'cooldown_tiro': cooldown_tiro, 'ultimo_tiro_tempo': 0, 'pontos_por_morte': pontos }

def server_spawnar_mothership(x, y, npc_id): return {'id': npc_id, 'tipo': 'mothership', 'x': float(x), 'y': float(y), 'angulo': 0.0, 'hp': 200, 'max_hp': 200, 'tamanho': 80, 'cooldown_tiro': 999999, 'ultimo_tiro_tempo': 0, 'pontos_por_morte': 100, 'ia_estado': 'VAGANDO', 'ia_alvo_retaliacao': None, 'ia_ultimo_hit_tempo': 0 }
def server_spawnar_boss_congelante(x, y, npc_id): return {'id': npc_id, 'tipo': 'boss_congelante', 'x': float(x), 'y': float(y), 'angulo': 0.0, 'hp': s.HP_BOSS_CONGELANTE, 'max_hp': s.HP_BOSS_CONGELANTE, 'tamanho': 100, 'cooldown_tiro': s.COOLDOWN_TIRO_CONGELANTE, 'ultimo_tiro_tempo': 0, 'pontos_por_morte': s.PONTOS_BOSS_CONGELANTE, 'ia_ultimo_spawn_minion': 0, 'ia_ultimo_hit_tempo': 0, 'ia_wander_target': None }
def server_spawnar_minion_mothership(owner, target_id, index, max_minions, npc_id_num): return {'id': f"minion_ms_{npc_id_num}", 'tipo': 'minion_mothership', 'owner_id': owner['id'], 'x': owner['x'], 'y': owner['y'], 'angulo': 0.0, 'hp': 2, 'max_hp': 2, 'tamanho': 15, 'pontos_por_morte': 1, 'cooldown_tiro': 1000, 'ultimo_tiro_tempo': 0, 'ia_alvo_id': target_id, 'ia_raio_orbita': owner['tamanho'] * 0.8 + random.randint(30, 60), 'ia_angulo_orbita': (index / max_minions) * 360, 'ia_vel_orbita': random.uniform(0.5, 1.0) }
def server_spawnar_minion_congelante(owner, target_id, index, max_minions, npc_id_num): return {'id': f"minion_bc_{npc_id_num}", 'tipo': 'minion_congelante', 'owner_id': owner['id'], 'x': owner['x'], 'y': owner['y'], 'angulo': 0.0, 'hp': HP_MINION_CONGELANTE, 'max_hp': HP_MINION_CONGELANTE, 'tamanho': 18, 'pontos_por_morte': PONTOS_MINION_CONGELANTE, 'cooldown_tiro': COOLDOWN_TIRO_MINION_CONGELANTE, 'ultimo_tiro_tempo': 0, 'ia_alvo_id': target_id, 'ia_raio_orbita': owner['tamanho'] * 0.7 + random.randint(30, 50), 'ia_angulo_orbita': (index / max_minions) * 360, 'ia_vel_orbita': random.uniform(0.5, 1.0) }

# --- CORREÇÃO: HP BAIXO PARA 1-HIT KILL ---
def server_spawnar_obstaculo(pos_referencia_lista, map_width, map_height, npc_id):
    x, y = server_calcular_posicao_spawn(pos_referencia_lista, map_width, map_height)
    raio = random.randint(s.OBSTACULO_RAIO_MIN, s.OBSTACULO_RAIO_MAX)
    
    # Cálculo proporcional de pontos (mantido)
    raio_norm = max(s.OBSTACULO_RAIO_MIN, min(raio, s.OBSTACULO_RAIO_MAX))
    range_r = s.OBSTACULO_RAIO_MAX - s.OBSTACULO_RAIO_MIN
    range_p = s.OBSTACULO_PONTOS_MAX - s.OBSTACULO_PONTOS_MIN
    pct = 0.0
    if range_r > 0: pct = (raio_norm - s.OBSTACULO_RAIO_MIN) / range_r
    pts = int(round(s.OBSTACULO_PONTOS_MIN + (pct * range_p)))
    
    # MODIFICAÇÃO: HP fixado em 0.1 para garantir que qualquer tiro destrua
    hp_calculado = 0.1 
    
    return {
        'id': npc_id,
        'tipo': 'obstaculo',
        'x': float(x),
        'y': float(y),
        'raio': raio,
        'hp': hp_calculado,
        'max_hp': hp_calculado,
        'pontos_por_morte': pts
    }