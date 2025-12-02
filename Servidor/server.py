# server.py

import socket
import threading
import random
import pygame # Importante para Vector2
import settings as s 
import multi.pvp_settings as pvp_s
import math 
import time 
import server_bot_ai 

# ==================================================================================
# 1. CONFIGURAÇÕES DO SERVIDOR
# ==================================================================================
HOST = '0.0.0.0'
PORT = 5555         
TICK_RATE = 60 

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

# ==================================================================================
# 2. FUNÇÕES AUXILIARES
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
    dx = attacker_x - target_x; dy = attacker_y - target_y
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
# LÓGICA DE PROJÉTEIS (HOMING SERVER-SIDE CORRIGIDO)
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
            
            # Correção do "Passou do alvo": usa Dot Product com tolerância maior (-0.5)
            # Se estiver muito perto (< 50), vira normal para evitar "mosquito"
            if dist < 50:
                 proj['tipo_proj'] = 'normal'
                 return

            curr_vel = pygame.math.Vector2(proj['vel_x'], proj['vel_y'])
            
            if curr_vel.length() > 0 and dist > 0:
                 # Se o produto escalar for negativo, significa que o alvo está "atrás" do movimento
                 # Paramos de perseguir para não ficar orbitando
                 if curr_vel.normalize().dot(desired_vec.normalize()) < -0.2: 
                     proj['tipo_proj'] = 'normal'
                     return

            if dist > 0:
                desired_dir = desired_vec.normalize()
                
                if curr_vel.length() == 0: curr_vel = desired_dir * proj['velocidade']
                
                # Fator de curva mais agressivo para acertar
                STEER_FACTOR = 0.20 
                
                new_dir = curr_vel.normalize().lerp(desired_dir, STEER_FACTOR)
                if new_dir.length() > 0: new_dir = new_dir.normalize()
                
                new_vel = new_dir * proj['velocidade']
                
                proj['vel_x'] = new_vel.x
                proj['vel_y'] = new_vel.y
        else:
            proj['tipo_proj'] = 'normal'

# ==================================================================================
# LÓGICA DE IA DOS INIMIGOS (MANTIDA)
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
    if (agora_ms - npc.get('ia_ultimo_hit_tempo', 0) < 1000) and npc.get('ia_alvo_retaliacao') is None:
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
        if not target: npc['ia_estado'] = 'VAGANDO'; npc['ia_alvo_retaliacao'] = None
        else:
            minions_vivos = [m for m in room_ref.npcs if m['tipo'] == 'minion_mothership' and m.get('owner_id') == npc['id']]
            if len(minions_vivos) == 0:
                 for i in range(MAX_MINIONS_MOTHERSHIP):
                     m = server_spawnar_minion_mothership(npc, t_id, i, MAX_MINIONS_MOTHERSHIP, room_ref.next_npc_id)
                     room_ref.npcs.append(m); room_ref.next_npc_id += 1
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
    if not npc.get('ia_wander_target') or (npc['x']-npc['ia_wander_target'][0])**2 + (npc['y']-npc['ia_wander_target'][1])**2 < 100**2:
        npc['ia_wander_target'] = (random.randint(100, s.MAP_WIDTH-100), random.randint(100, s.MAP_HEIGHT-100))
    wx, wy = npc['ia_wander_target']
    dx, dy = wx - npc['x'], wy - npc['y']
    dist = math.sqrt(dx**2 + dy**2)
    if dist > 5: npc['x'] += (dx/dist) * 1.0; npc['y'] += (dy/dist) * 1.0
    if (agora_ms - npc.get('ia_ultimo_hit_tempo', 0) < 1000) and (agora_ms - npc.get('ia_ultimo_spawn_minion', 0) > COOLDOWN_SPAWN_MINION_CONGELANTE):
        minions = [m for m in room_ref.npcs if m['tipo'] == 'minion_congelante' and m.get('owner_id') == npc['id']]
        if len(minions) < MAX_MINIONS_CONGELANTE:
            npc['ia_ultimo_spawn_minion'] = agora_ms
            m = server_spawnar_minion_congelante(npc, target['nome'], len(minions), MAX_MINIONS_CONGELANTE, room_ref.next_npc_id)
            room_ref.npcs.append(m); room_ref.next_npc_id += 1
    if agora_ms - npc.get('ultimo_tiro_tempo', 0) > s.COOLDOWN_TIRO_CONGELANTE:
        npc['ultimo_tiro_tempo'] = agora_ms
        tx, ty = target['x'], target['y']
        vx, vy = tx - npc['x'], ty - npc['y']
        d_t = math.sqrt(vx**2 + vy**2) + 0.1
        vel_x = (vx/d_t) * VELOCIDADE_PROJ_CONGELANTE
        vel_y = (vy/d_t) * VELOCIDADE_PROJ_CONGELANTE
        return {'id': f"{npc['id']}_{agora_ms}", 'owner_nome': npc['id'], 'x': npc['x'], 'y': npc['y'], 'pos_inicial_x': npc['x'], 'pos_inicial_y': npc['y'], 'dano': 1, 'tipo': 'npc', 'tipo_proj': 'congelante', 'velocidade': VELOCIDADE_PROJ_CONGELANTE, 'vel_x': vel_x, 'vel_y': vel_y, 'alvo_id': target['nome'], 'timestamp_criacao': agora_ms}
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

def _build_player_state_list(player_dict, agora_ms):
    lista_de_estados = []
    for state in player_dict.values():
        if state.get('handshake_completo', True): 
            regen = 1 if state.get('esta_regenerando', False) else 0
            is_lento = 1 if agora_ms < state.get('tempo_fim_lentidao', 0) else 0
            is_congelado = 1 if agora_ms < state.get('tempo_fim_congelamento', 0) else 0
            is_pre_match = 1 if state.get('is_pre_match', False) else 0
            estado_str = (
                f"{state['nome']}:{state['x']:.1f}:{state['y']:.1f}:{state['angulo']:.0f}:{state['hp']:.1f}:{state['max_hp']:.1f}"
                f":{state['pontos']}:{regen}:{state['pontos_upgrade_disponiveis']}:{state['total_upgrades_feitos']}"
                f":{state['nivel_motor']}:{state['nivel_dano']}:{state['nivel_max_vida']}"
                f":{state['nivel_escudo']}:{state['nivel_aux']}"
                f":{is_lento}:{is_congelado}:{is_pre_match}:{state.get('last_hit_angle', 0):.2f}"
            )
            lista_de_estados.append(estado_str)
    return lista_de_estados

# ==================================================================================
# 3. CLASSES DE SALA
# ==================================================================================

class GameRoom:
    def __init__(self, room_id, game_mode, max_players):
        self.room_id = room_id; self.game_mode = game_mode; self.max_players = max_players
        self.players = {}; self.projectiles = []; self.lock = threading.Lock(); self.agora_ms = 0
    def broadcast(self, message_bytes):
        dead_conns = []
        with self.lock: recipients = [k for k in self.players.keys() if isinstance(k, socket.socket)]
        for conn in recipients:
            try: conn.sendall(message_bytes)
            except: dead_conns.append(conn)
        if dead_conns:
            with self.lock:
                for c in dead_conns:
                    if c in self.players: del self.players[c]
    def remove_player(self, conn):
        with self.lock:
            if conn in self.players: print(f"[SALA {self.room_id}] {self.players[conn]['nome']} saiu."); del self.players[conn]
    def is_full(self):
        with self.lock: return len([k for k in self.players if isinstance(k, socket.socket)]) >= self.max_players

# --- SALA PVE ---
class PveRoom(GameRoom):
    def __init__(self, room_id):
        super().__init__(room_id, "PVE", MAX_PLAYERS_PVE)
        self.npcs = []; self.next_npc_id = 0
        self.state_globals = {'player_states': self.players, 'network_npcs': self.npcs}
        self.logic_callbacks = {'spawn_calculator': server_calcular_posicao_spawn, 'upgrade_purchaser': server_comprar_upgrade}
        self.bot_manager = server_bot_ai.ServerBotManager(s, self.state_globals, self.logic_callbacks)
    def update(self):
        self.agora_ms = int(time.time() * 1000)
        with self.lock:
            humanos_count = sum(1 for p in self.players.values() if not p.get('is_bot'))
            MAX_ENTIDADES_SALA = 10
            MAX_BOTS_DESEJADOS = 4
            slots_livres = max(0, MAX_ENTIDADES_SALA - humanos_count)
            target_bots = min(MAX_BOTS_DESEJADOS, slots_livres)

            bots_remover = self.bot_manager.manage_bot_population(target_bots)
            for nome in bots_remover:
                key_to_remove = None
                for k, v in self.players.items():
                    if v['nome'] == nome: key_to_remove = k; break
                if key_to_remove: del self.players[key_to_remove]
            self._update_logic()
            
    def _update_logic(self):
        living_players = [p for p in self.players.values() if p.get('handshake_completo') and p.get('hp') > 0]
        living_targets = living_players + self.npcs 
        novos_projeteis = []
        for p in living_players:
            if p.get('is_bot'): self.bot_manager.process_bot_logic(p, living_players, self.agora_ms)
            if p.get('esta_regenerando'):
                if (p['teclas']['w'] or p['teclas']['a'] or p['teclas']['s'] or p['teclas']['d'] or p['alvo_mouse']): p['esta_regenerando'] = False
                elif p['hp'] < p['max_hp']:
                    if self.agora_ms - p.get('ultimo_tick_regeneracao', 0) > REGEN_TICK_RATE_MS:
                        p['hp'] = min(p['max_hp'], p['hp'] + REGEN_POR_TICK); p['ultimo_tick_regeneracao'] = self.agora_ms
                else: p['esta_regenerando'] = False
            new_proj = update_player_logic(p, living_targets, self.agora_ms, s.MAP_WIDTH, s.MAP_HEIGHT)
            if new_proj: novos_projeteis.append(new_proj)
            if p.get('nivel_aux', 0) > 0 and p.get('alvo_lock'):
                t_id = p['alvo_lock']; target = next((x for x in living_targets if x.get('id', x.get('nome')) == t_id), None)
                if target:
                    for i in range(p['nivel_aux']):
                        if self.agora_ms > p['aux_cooldowns'][i]:
                            off_x, off_y = _rotate_vector(AUX_POSICOES[i][0], AUX_POSICOES[i][1], -p['angulo'])
                            ax, ay = p['x'] + off_x, p['y'] + off_y
                            dist_sq = (ax-target['x'])**2 + (ay-target['y'])**2
                            if dist_sq < AUX_DISTANCIA_TIRO_SQ:
                                p['aux_cooldowns'][i] = self.agora_ms + AUX_COOLDOWN_TIRO
                                dist = math.sqrt(dist_sq)
                                if dist > 0: dir_x = (target['x'] - ax) / dist; dir_y = (target['y'] - ay) / dist
                                else: dir_x, dir_y = 0, -1
                                tipo_aux = 'player_pve'
                                if p['nivel_dano'] >= s.MAX_NIVEL_DANO: tipo_aux += '_max'
                                novos_projeteis.append({'id': f"{p['nome']}_aux{i}_{self.agora_ms}", 'owner_nome': p['nome'], 'x': ax, 'y': ay, 'pos_inicial_x': ax, 'pos_inicial_y': ay, 'dano': s.DANO_POR_NIVEL[p['nivel_dano']], 'tipo': tipo_aux, 'tipo_proj': 'teleguiado', 'velocidade': 14, 'alvo_id': t_id, 'timestamp_criacao': self.agora_ms, 'vel_x': dir_x * 14, 'vel_y': dir_y * 14})
        for npc in self.npcs:
            if npc.get('hp') <= 0: continue
            new_proj = None
            if npc['tipo'] == 'mothership': update_mothership_logic(npc, self.players, self.agora_ms, self)
            elif npc['tipo'] == 'boss_congelante': new_proj = update_boss_congelante_logic(npc, self.players, self.agora_ms, self)
            elif 'minion' in npc['tipo']: new_proj = update_minion_logic(npc, self.players, self.agora_ms, self)
            else: new_proj = update_npc_generic_logic(npc, self.players, self.agora_ms)
            if new_proj: novos_projeteis.append(new_proj)
        self.projectiles.extend(novos_projeteis)
        
        toremove_proj = []; toremove_npc = []
        for proj in self.projectiles:
            # --- ATUALIZAÇÃO FÍSICA PROJÉTEIS (Incluindo Homing) ---
            update_projectile_physics(proj, living_targets, self.agora_ms)

            if (proj['x']-proj['pos_inicial_x'])**2 + (proj['y']-proj['pos_inicial_y'])**2 > MAX_DISTANCIA_TIRO_SQ: toremove_proj.append(proj); continue
            if proj['tipo'] == 'player_pve' or proj['tipo'] == 'player_pve_max':
                hit = False
                for npc in self.npcs:
                    if npc['hp'] <= 0: continue
                    if (npc['x']-proj['x'])**2 + (npc['y']-proj['y'])**2 < (npc['tamanho']/2 + 10)**2:
                        npc['hp'] -= proj['dano']; npc['ia_ultimo_hit_tempo'] = self.agora_ms; hit = True
                        if npc['hp'] <= 0:
                            toremove_npc.append(npc)
                            owner = next((p for p in self.players.values() if p['nome'] == proj['owner_nome']), None)
                            if owner: server_ganhar_pontos(owner, npc.get('pontos_por_morte', 5))
                        break
                if not hit:
                    for target in living_players:
                        if target['nome'] == proj['owner_nome']: continue
                        if self.agora_ms - target.get('spawn_time', 0) < SPAWN_PROTECTION_MS: continue # Proteção de Spawn
                        
                        if (target['x']-proj['x'])**2 + (target['y']-proj['y'])**2 < COLISAO_JOGADOR_PROJ_DIST_SQ:
                            dano_base = proj['dano']; fator_escudo = min(target['nivel_escudo'] * REDUCAO_DANO_POR_NIVEL, 75) / 100.0
                            target['hp'] -= dano_base * (1.0 - fator_escudo); target['ultimo_hit_tempo'] = self.agora_ms; target['esta_regenerando'] = False
                            if target.get('is_bot'): target['bot_last_attacker_id'] = proj['owner_nome']
                            target['last_hit_angle'] = calc_hit_angle_rad(target['x'], target['y'], proj['x'], proj['y'])
                            hit = True; break
                if hit: toremove_proj.append(proj); continue
            elif proj['tipo'] == 'npc':
                hit = False
                for p in living_players:
                    if self.agora_ms - p.get('spawn_time', 0) < SPAWN_PROTECTION_MS: continue # Proteção de Spawn
                    
                    if (p['x']-proj['x'])**2 + (p['y']-proj['y'])**2 < COLISAO_JOGADOR_PROJ_DIST_SQ:
                        dano = 1 * (1 - min(p['nivel_escudo'] * REDUCAO_DANO_POR_NIVEL / 100.0, 0.75)); p['hp'] -= dano
                        p['ultimo_hit_tempo'] = self.agora_ms; p['esta_regenerando'] = False
                        if proj.get('tipo_proj') == 'congelante': p['tempo_fim_congelamento'] = self.agora_ms + DURACAO_CONGELAMENTO_MS
                        elif proj.get('tipo_proj') == 'teleguiado_lento': p['tempo_fim_lentidao'] = self.agora_ms + DURACAO_LENTIDAO_MS
                        p['last_hit_angle'] = calc_hit_angle_rad(p['x'], p['y'], proj['x'], proj['y'])
                        hit = True; break
                if hit: toremove_proj.append(proj); continue
        
        for p in living_players:
            for npc in self.npcs:
                if npc.get('hp') <= 0: continue
                raio_npc = npc.get('tamanho', 30) / 2
                raio_player = 15
                dist_colisao_sq = (raio_npc + raio_player) ** 2
                
                dist_sq = (p['x'] - npc['x'])**2 + (p['y'] - npc['y'])**2
                if dist_sq < dist_colisao_sq:
                    if self.agora_ms - p.get('spawn_time', 0) < SPAWN_PROTECTION_MS: continue # Proteção
                    
                    dano_npc = 1
                    if npc['tipo'] == 'bomba': dano_npc = 3
                    
                    fator_escudo = min(p['nivel_escudo'] * REDUCAO_DANO_POR_NIVEL, 75) / 100.0
                    p['hp'] -= dano_npc * (1.0 - fator_escudo)
                    p['ultimo_hit_tempo'] = self.agora_ms
                    p['esta_regenerando'] = False
                    p['last_hit_angle'] = calc_hit_angle_rad(p['x'], p['y'], npc['x'], npc['y'])
                    
                    npc['hp'] -= 1 
                    npc['ia_ultimo_hit_tempo'] = self.agora_ms
                    if npc['tipo'] == 'bomba': npc['hp'] = 0 
                    
                    if npc['hp'] <= 0:
                        toremove_npc.append(npc)
                        server_ganhar_pontos(p, npc.get('pontos_por_morte', 5))
        
        for p in toremove_proj: 
            if p in self.projectiles: self.projectiles.remove(p)
        for n in toremove_npc:
            if n in self.npcs: self.npcs.remove(n)
        if living_players:
             count_normais = sum(1 for n in self.npcs if n['hp'] > 0 and n['tipo'] not in ['mothership', 'boss_congelante', 'minion_mothership', 'minion_congelante'])
             if count_normais < s.MAX_INIMIGOS: refs = [(p['x'], p['y']) for p in living_players]; sx, sy = server_calcular_posicao_spawn(refs, s.MAP_WIDTH, s.MAP_HEIGHT); self.npcs.append(server_spawnar_inimigo_aleatorio(sx, sy, f"npc_{self.next_npc_id}")); self.next_npc_id += 1
             count_ms = sum(1 for n in self.npcs if n['hp'] > 0 and n['tipo'] == 'mothership')
             if count_ms < s.MAX_MOTHERSHIPS: refs = [(p['x'], p['y']) for p in living_players]; sx, sy = server_calcular_posicao_spawn(refs, s.MAP_WIDTH, s.MAP_HEIGHT); self.npcs.append(server_spawnar_mothership(sx, sy, f"ms_{self.next_npc_id}")); self.next_npc_id += 1
             count_bc = sum(1 for n in self.npcs if n['hp'] > 0 and n['tipo'] == 'boss_congelante')
             if count_bc < s.MAX_BOSS_CONGELANTE: refs = [(p['x'], p['y']) for p in living_players]; sx, sy = server_calcular_posicao_spawn(refs, s.MAP_WIDTH, s.MAP_HEIGHT); self.npcs.append(server_spawnar_boss_congelante(sx, sy, f"bc_{self.next_npc_id}")); self.next_npc_id += 1
    def get_state_bytes(self):
        with self.lock:
            pl_str = ";".join(_build_player_state_list(self.players, self.agora_ms))
            pr_str = ";".join([f"{p['id']}:{p['x']:.1f}:{p['y']:.1f}:{p['tipo']}:{p.get('tipo_proj','normal')}" for p in self.projectiles])
            np_str = ";".join([f"{n['id']}:{n['tipo']}:{n['x']:.1f}:{n['y']:.1f}:{n['angulo']:.0f}:{n['hp']}:{n['max_hp']}:{n['tamanho']}" for n in self.npcs if n['hp'] > 0])
            return f"STATE|{pl_str}|PROJ|{pr_str}|NPC|{np_str}\n".encode('utf-8')

# --- SALA PVP ---
class PvpRoom(GameRoom):
    def __init__(self, room_id):
        super().__init__(room_id, "PVP", MAX_PLAYERS_PVP)
        self.lobby_state = "WAITING"; self.timer_fim = 0; self.timer_partida = 0; self.winner = ""; self.restart_ts = 0
    def reset_match(self):
        print(f"[SALA {self.room_id}] Resetando PVP."); self.lobby_state = "WAITING"; self.winner = ""; self.projectiles.clear()
        for p in self.players.values(): p['x'] = pvp_s.SPAWN_LOBBY.x; p['y'] = pvp_s.SPAWN_LOBBY.y; p['hp'] = p['max_hp']; p['is_pre_match'] = False; p['esta_regenerando'] = False; p['alvo_lock'] = None
    def update(self):
        self.agora_ms = int(time.time() * 1000)
        with self.lock:
            if not self.players and self.lobby_state != "WAITING": self.reset_match(); return
            if self.lobby_state == "WAITING":
                self._update_physics_pvp()
                if len(self.players) >= 4: self.lobby_state = "COUNTDOWN"; self.timer_fim = self.agora_ms + LOBBY_COUNTDOWN_MS
            elif self.lobby_state == "COUNTDOWN":
                self._update_physics_pvp()
                if len(self.players) < 4: self.lobby_state = "WAITING"
                elif self.agora_ms > self.timer_fim:
                    self.lobby_state = "PRE_MATCH"; self.timer_fim = self.agora_ms + PRE_MATCH_FREEZE_MS; self.timer_partida = self.agora_ms + PRE_MATCH_FREEZE_MS + PARTIDA_COUNTDOWN_MS; lista = list(self.players.values())
                    for i, p in enumerate(lista):
                        if i < len(pvp_s.SPAWN_POSICOES): p['x'] = pvp_s.SPAWN_POSICOES[i].x; p['y'] = pvp_s.SPAWN_POSICOES[i].y; p['hp'] = p['max_hp']; p['is_pre_match'] = True; p['alvo_mouse'] = None; p['alvo_lock'] = None; p['teclas'] = {'w':False, 'a':False, 's':False, 'd':False, 'space':False}
            elif self.lobby_state == "PRE_MATCH":
                if self.agora_ms > self.timer_fim: self.lobby_state = "PLAYING"; 
                for p in self.players.values(): p['is_pre_match'] = False
            elif self.lobby_state == "PLAYING":
                self._update_physics_pvp()
                vivos = [p for p in self.players.values() if p['hp'] > 0]
                if len(vivos) <= 1 or self.agora_ms > self.timer_partida: self.lobby_state = "GAME_OVER"; self.winner = vivos[0]['nome'] if vivos else "Empate"; self.restart_ts = self.agora_ms + RESTART_DELAY_MS
            elif self.lobby_state == "GAME_OVER":
                if self.agora_ms > self.restart_ts:
                    if len(self.players) > 0: 
                        self.reset_match() 
                        if len(self.players) >= 4: self.lobby_state = "COUNTDOWN"; self.timer_fim = self.agora_ms + LOBBY_COUNTDOWN_MS
                        else: self.lobby_state = "WAITING"
                    else: self.lobby_state = "WAITING"
    def _update_physics_pvp(self):
        living = [p for p in self.players.values() if p['hp'] > 0]
        for p in living:
            if p.get('esta_regenerando'):
                if (p['teclas']['w'] or p['teclas']['a'] or p['teclas']['s'] or p['teclas']['d'] or p['alvo_mouse']): p['esta_regenerando'] = False
                elif p['hp'] < p['max_hp']:
                     if self.agora_ms - p.get('ultimo_tick_regeneracao', 0) > REGEN_TICK_RATE_MS: p['hp'] = min(p['max_hp'], p['hp'] + REGEN_POR_TICK); p['ultimo_tick_regeneracao'] = self.agora_ms
                else: p['esta_regenerando'] = False
            new_p = update_player_logic(p, living, self.agora_ms, pvp_s.MAP_WIDTH, pvp_s.MAP_HEIGHT)
            if new_p: self.projectiles.append(new_p)
            if p.get('nivel_aux', 0) > 0 and p.get('alvo_lock'):
                t_id = p['alvo_lock']; target = next((x for x in living if x.get('nome') == t_id), None)
                if target:
                    for i in range(p['nivel_aux']):
                        if self.agora_ms > p['aux_cooldowns'][i]:
                            off_x, off_y = _rotate_vector(AUX_POSICOES[i][0], AUX_POSICOES[i][1], -p['angulo'])
                            ax, ay = p['x'] + off_x, p['y'] + off_y
                            dist_sq = (ax-target['x'])**2 + (ay-target['y'])**2
                            if dist_sq < AUX_DISTANCIA_TIRO_SQ:
                                p['aux_cooldowns'][i] = self.agora_ms + AUX_COOLDOWN_TIRO
                                dist = math.sqrt(dist_sq)
                                if dist > 0: dir_x = (target['x'] - ax) / dist; dir_y = (target['y'] - ay) / dist
                                else: dir_x, dir_y = 0, -1
                                tipo_aux = 'player_pvp'
                                if p['nivel_dano'] >= s.MAX_NIVEL_DANO: tipo_aux += '_max'
                                self.projectiles.append({'id': f"{p['nome']}_aux{i}_{self.agora_ms}", 'owner_nome': p['nome'], 'x': ax, 'y': ay, 'pos_inicial_x': ax, 'pos_inicial_y': ay, 'dano': s.DANO_POR_NIVEL[p['nivel_dano']], 'tipo': tipo_aux, 'tipo_proj': 'teleguiado', 'velocidade': 14, 'alvo_id': t_id, 'timestamp_criacao': self.agora_ms, 'vel_x': dir_x * 14, 'vel_y': dir_y * 14})
        toremove = []
        for proj in self.projectiles:
            # --- ATUALIZAÇÃO FÍSICA PVP ---
            update_projectile_physics(proj, living, self.agora_ms)

            if not (0 <= proj['x'] <= pvp_s.MAP_WIDTH and 0 <= proj['y'] <= pvp_s.MAP_HEIGHT): toremove.append(proj); continue
            for target in living:
                if target['nome'] != proj['owner_nome']:
                    if (target['x']-proj['x'])**2 + (target['y']-proj['y'])**2 < COLISAO_JOGADOR_PROJ_DIST_SQ:
                        if self.lobby_state == "PLAYING":
                            dano_base = proj['dano']; fator_escudo = min(target['nivel_escudo'] * REDUCAO_DANO_POR_NIVEL, 75) / 100.0
                            target['hp'] -= dano_base * (1.0 - fator_escudo); target['esta_regenerando'] = False
                            target['last_hit_angle'] = calc_hit_angle_rad(target['x'], target['y'], proj['x'], proj['y'])
                        toremove.append(proj); break
        for p in toremove:
            if p in self.projectiles: self.projectiles.remove(p)
    def get_state_bytes(self):
        with self.lock:
            pl_str = ";".join(_build_player_state_list(self.players, self.agora_ms))
            pr_str = ";".join([f"{p['id']}:{p['x']:.1f}:{p['y']:.1f}:{p['tipo']}:{p.get('tipo_proj','normal')}" for p in self.projectiles])
            lt = max(0, int((self.timer_fim - self.agora_ms)/1000)) if self.lobby_state == "COUNTDOWN" else 0
            if self.lobby_state == "GAME_OVER": lt = max(0, int((self.restart_ts - self.agora_ms)/1000))
            mt = max(0, int((self.timer_partida - self.agora_ms)/1000)) if self.lobby_state in ["PRE_MATCH", "PLAYING"] else 0
            status = f"PVP_STATUS_UPDATE|{len(self.players)}|{lt}|{mt}|{self.lobby_state}|{self.winner}\n"
            return status.encode('utf-8') + f"STATE|{pl_str}|PROJ|{pr_str}|NPC|\n".encode('utf-8')

all_rooms = []
for i in range(QTD_SALAS_PVE): all_rooms.append(PveRoom(f"PVE_{i+1}"))
for i in range(QTD_SALAS_PVP): all_rooms.append(PvpRoom(f"PVP_{i+1}"))
def find_room(mode):
    for r in all_rooms:
        if r.game_mode == mode:
            if mode == "PVP" and r.lobby_state not in ["WAITING", "GAME_OVER"]: continue
            if not r.is_full(): return r
    return None
def handle_client(conn, addr):
    print(f"[LOGIN] {addr}")
    try:
        data = conn.recv(1024).decode('utf-8'); 
        if not data: conn.close(); return
        parts = data.strip().split('|'); name_req = parts[0]; mode = parts[1] if len(parts) > 1 else "PVE"
        room = find_room(mode)
        if not room: conn.sendall(b"REJEITADO|Sem salas\n"); conn.close(); return
        name = name_req
        with room.lock:
            exist = [p['nome'] for p in room.players.values()]; i=1
            while name in exist: name = f"{name_req}_{i}"; i+=1
        sx, sy = 0, 0
        if mode == "PVE":
            with room.lock: refs = [(p['x'], p['y']) for p in room.players.values()]
            sx, sy = server_calcular_posicao_spawn(refs, s.MAP_WIDTH, s.MAP_HEIGHT)
        else: sx, sy = pvp_s.SPAWN_LOBBY.x, pvp_s.SPAWN_LOBBY.y
        p_state = {'conn': conn, 'nome': name, 'is_bot': False, 'is_pvp': (mode=="PVP"), 'handshake_completo': True, 'x': sx, 'y': sy, 'angulo': 0, 'hp': float(s.VIDA_POR_NIVEL[1]), 'max_hp': float(s.VIDA_POR_NIVEL[1]), 'teclas': {'w':False, 'a':False, 's':False, 'd':False, 'space':False}, 'alvo_mouse': None, 'alvo_lock': None, 'ultimo_tiro_tempo': 0, 'cooldown_tiro': COOLDOWN_TIRO, 'pontos': 0, 'pontos_upgrade_disponiveis': (10 if mode == "PVP" else 0), 'total_upgrades_feitos': 0, '_pontos_acumulados_para_upgrade': 0, '_limiar_pontos_atual': PONTOS_LIMIARES_PARA_UPGRADE[0], '_indice_limiar': 0, 'nivel_motor': 1, 'nivel_dano': 1, 'nivel_max_vida': 1, 'nivel_escudo': 0, 'nivel_aux': 0, 'aux_cooldowns': [0]*4, 'last_hit_angle': 0, 'spawn_time': int(time.time()*1000)}
        with room.lock: room.players[conn] = p_state
        prefix = "BEMVINDO_PVP" if mode == "PVP" else "BEMVINDO"
        conn.sendall(f"{prefix}|{name}|{int(sx)}|{int(sy)}\n".encode('utf-8')); print(f"[JOIN] {name} -> {room.room_id}")
        while True:
            d = conn.recv(2048); 
            if not d: break
            lines = d.decode('utf-8').splitlines()
            with room.lock:
                if conn not in room.players: break
                me = room.players[conn]
                if me['hp'] <= 0 and not me['is_pvp'] and "RESPAWN_ME" in lines:
                        refs = [(p['x'], p['y']) for p in room.players.values()]; rx, ry = server_calcular_posicao_spawn(refs, s.MAP_WIDTH, s.MAP_HEIGHT)
                        me['x'] = rx; me['y'] = ry; me['nivel_max_vida'] = 1; me['max_hp'] = float(s.VIDA_POR_NIVEL[1]); me['hp'] = me['max_hp']; me['alvo_lock'] = None; me['pontos'] = 0; me['pontos_upgrade_disponiveis'] = 0; me['total_upgrades_feitos'] = 0; me['_pontos_acumulados_para_upgrade'] = 0; me['_limiar_pontos_atual'] = PONTOS_LIMIARES_PARA_UPGRADE[0]; me['_indice_limiar'] = 0; me['nivel_motor'] = 1; me['nivel_dano'] = 1; me['nivel_escudo'] = 0; me['nivel_aux'] = 0; me['aux_cooldowns'] = [0]*4; me['tempo_fim_lentidao'] = 0; me['tempo_fim_congelamento'] = 0; me['spawn_time'] = int(time.time()*1000); continue
                for l in lines:
                    if l == "W_DOWN": me['teclas']['w'] = True; me['alvo_mouse'] = None
                    elif l == "W_UP": me['teclas']['w'] = False
                    elif l == "A_DOWN": me['teclas']['a'] = True
                    elif l == "A_UP": me['teclas']['a'] = False
                    elif l == "S_DOWN": me['teclas']['s'] = True; me['alvo_mouse'] = None
                    elif l == "S_UP": me['teclas']['s'] = False
                    elif l == "D_DOWN": me['teclas']['d'] = True
                    elif l == "D_UP": me['teclas']['d'] = False
                    elif l == "SPACE_DOWN": me['teclas']['space'] = True
                    elif l == "SPACE_UP": me['teclas']['space'] = False
                    elif l.startswith("CLICK_MOVE|"): _, x, y = l.split('|'); me['alvo_mouse'] = (int(x), int(y)); me['teclas']['w'] = False; me['teclas']['s'] = False
                    elif l.startswith("CLICK_TARGET|"):
                        _, cx, cy = l.split('|'); cx=int(cx); cy=int(cy); targets = list(room.players.values())
                        if isinstance(room, PveRoom): targets += room.npcs
                        best_d = float('inf'); best_id = None
                        for t in targets:
                            if t.get('nome') == me['nome']: continue
                            if t.get('hp',0) <= 0: continue
                            dist = (t['x']-cx)**2 + (t['y']-cy)**2
                            if dist < TARGET_CLICK_SIZE_SQ and dist < best_d: best_d = dist; best_id = t.get('id', t.get('nome'))
                        me['alvo_lock'] = best_id
                    elif l == "TOGGLE_REGEN":
                        if not me.get('esta_regenerando') and me['hp'] < me['max_hp']: me['esta_regenerando'] = True
                        else: me['esta_regenerando'] = False
                    elif l.startswith("BUY_UPGRADE|"): server_comprar_upgrade(me, l.split('|')[1])
                    elif l == "ENTER_SPECTATOR": me['hp'] = 0
    except Exception as e: print(f"[ERROR] {addr}: {e}")
    finally:
        if 'room' in locals() and room: room.remove_player(conn)
        conn.close()
def connection_listener(sock):
    while True:
        try: conn, addr = sock.accept(); threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        except: break
def server_loop():
    while True:
        st = time.time()
        for r in all_rooms: r.update(); r.broadcast(r.get_state_bytes())
        dt = time.time() - st; wait = (1.0/TICK_RATE) - dt
        if wait > 0: time.sleep(wait)
def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try: sock.bind((HOST, PORT))
    except: print(f"Porta {PORT} ocupada."); return
    sock.listen(32); print(f"Server {HOST}:{PORT} | PVE: {QTD_SALAS_PVE} | PVP: {QTD_SALAS_PVP}")
    if not hasattr(s, 'DANO_POR_NIVEL'): s.DANO_POR_NIVEL = [0, 0.7, 0.9, 1.2, 1.4, 1.6]
    if not hasattr(s, 'VIDA_POR_NIVEL'): s.VIDA_POR_NIVEL = [0, 5, 6, 8, 9, 10]
    threading.Thread(target=server_loop, daemon=True).start(); threading.Thread(target=connection_listener, args=(sock,), daemon=True).start()
    try:
        while True:
            cmd = input("> ")
            if cmd == "status":
                for r in all_rooms: print(f"[{r.room_id}] {len(r.players)}/{r.max_players} players")
    except KeyboardInterrupt: pass
    finally: sock.close()
if __name__ == "__main__": main()