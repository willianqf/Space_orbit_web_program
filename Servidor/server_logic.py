# Servidor/server_logic.py
import random
import math
import time
import settings as s
import multi.pvp_settings as pvp_s

class Vector2:
    __slots__ = ('x', 'y')
    def __init__(self, x=0.0, y=0.0): self.x = float(x); self.y = float(y)
    def __sub__(self, other): return Vector2(self.x - other.x, self.y - other.y)
    def __add__(self, other): return Vector2(self.x + other.x, self.y + other.y)
    def __mul__(self, scalar): return Vector2(self.x * scalar, self.y * scalar)
    def __rmul__(self, scalar): return Vector2(self.x * scalar, self.y * scalar)
    def __truediv__(self, scalar): return Vector2(0, 0) if scalar == 0 else Vector2(self.x / scalar, self.y / scalar)
    def __repr__(self): return f"Vector2({self.x:.2f}, {self.y:.2f})"
    def length(self): return math.sqrt(self.x * self.x + self.y * self.y)
    def length_squared(self): return self.x * self.x + self.y * self.y
    def normalize(self):
        length = self.length()
        return Vector2(self.x / length, self.y / length) if length > 0 else Vector2(0, 0)
    def scale_to_length(self, new_length):
        length = self.length()
        if length > 0: factor = new_length / length; return Vector2(self.x * factor, self.y * factor)
        return Vector2(0, 0)
    def rotate(self, angle_degrees):
        rad = math.radians(angle_degrees); cos_a = math.cos(rad); sin_a = math.sin(rad)
        return Vector2(self.x * cos_a - self.y * sin_a, self.x * sin_a + self.y * cos_a)
    def dot(self, other): return self.x * other.x + self.y * other.y
    def distance_to(self, other): return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)
    def distance_squared_to(self, other): return (self.x - other.x)**2 + (self.y - other.y)**2

QTD_SALAS_PVE = 3; MAX_PLAYERS_PVE = 16; QTD_SALAS_PVP = 4; MAX_PLAYERS_PVP = pvp_s.MAX_JOGADORES_PVP
AOI_RADIUS_SQ = 3500**2; COLISAO_JOGADOR_PROJ_DIST_SQ = (getattr(s, 'PLAYER_COLLISION_RADIUS', 15) + getattr(s, 'TIRO_RAIO', 5))**2; COLISAO_JOGADOR_NPC_DIST_SQ = (15 + 15)**2; NPC_DETECTION_RANGE_SQ = 3000**2; MAX_DISTANCIA_TIRO_SQ = s.MAX_DISTANCIA_TIRO**2
LOBBY_COUNTDOWN_MS = pvp_s.PVP_LOBBY_COUNTDOWN_SEGUNDOS * 1000; PARTIDA_COUNTDOWN_MS = pvp_s.PVP_PARTIDA_DURACAO_SEGUNDOS * 1000; PRE_MATCH_FREEZE_MS = 5000; RESTART_DELAY_MS = 10000; SPAWN_PROTECTION_MS = 3000
COOLDOWN_TIRO = 450; OFFSET_PONTA_TIRO = s.OFFSET_PONTA_TIRO; VELOCIDADE_PERSEGUIDOR = 2.0; DISTANCIA_PARAR_PERSEGUIDOR_SQ = 200**2; SPAWN_DIST_MIN = s.SPAWN_DIST_MIN; COOLDOWN_TIRO_PERSEGUIDOR = 2000; DISTANCIA_TIRO_PERSEGUIDOR_SQ = 500**2; VELOCIDADE_PROJETIL_NPC = 7; MAX_TARGET_LOCK_DISTANCE_SQ = s.MAX_TARGET_LOCK_DISTANCE**2; TARGET_CLICK_SIZE_SQ = (s.TARGET_CLICK_SIZE / 2)**2; REGEN_POR_TICK = s.REGEN_POR_TICK; REGEN_TICK_RATE_MS = s.REGEN_TICK_RATE; REDUCAO_DANO_POR_NIVEL = s.REDUCAO_DANO_POR_NIVEL
VELOCIDADE_PROJETIL_TELE = 14; DURACAO_PROJETIL_TELE_MS = 2000; TURN_SPEED_TELE = 0.15; VELOCIDADE_PROJ_LENTO = 9.0; DURACAO_PROJ_LENTO_MS = 5000; VELOCIDADE_PROJ_CONGELANTE = 8.0; DURACAO_PROJ_CONGELANTE_MS = 700; DURACAO_LENTIDAO_MS = 6000; DURACAO_CONGELAMENTO_MS = 2000
KAMIKAZE_DIST_DETONACAO_SQ = s.KAMIKAZE_DIST_DETONACAO**2; KAMIKAZE_RAIO_EXPLOSAO_SQ = s.KAMIKAZE_RAIO_EXPLOSAO**2
COOLDOWN_SPAWN_MINION_CONGELANTE = 10000; MAX_MINIONS_CONGELANTE = 6; MAX_MINIONS_MOTHERSHIP = 8; COOLDOWN_TIRO_MINION_CONGELANTE = 600; HP_MINION_CONGELANTE = 10; PONTOS_MINION_CONGELANTE = 5; VELOCIDADE_MINION_CONGELANTE = 2.5; MINION_CONGELANTE_LEASH_RANGE = 1500; MAX_AUXILIARES = 4; CUSTOS_AUXILIARES = s.CUSTOS_AUXILIARES; AUX_POSICOES = [(-40, 20), (40, 20), (-50, -10), (50, -10)]; AUX_COOLDOWN_TIRO = 1000; AUX_DISTANCIA_TIRO_SQ = 1000**2
MAX_TOTAL_UPGRADES = s.MAX_TOTAL_UPGRADES; MAX_NIVEL_MOTOR = s.MAX_NIVEL_MOTOR; MAX_NIVEL_DANO = s.MAX_NIVEL_DANO; MAX_NIVEL_ESCUDO = s.MAX_NIVEL_ESCUDO
PONTOS_LIMIARES_PARA_UPGRADE = list(s.PONTOS_LIMIARES_PARA_UPGRADE) if hasattr(s, 'PONTOS_LIMIARES_PARA_UPGRADE') else [100, 150, 200, 250, 300]
PONTOS_SCORE_PARA_MUDAR_LIMIAR = list(s.PONTOS_SCORE_PARA_MUDAR_LIMIAR) if hasattr(s, 'PONTOS_SCORE_PARA_MUDAR_LIMIAR') else [500, 1000, 2000, 4000]
VIDA_POR_NIVEL = s.VIDA_POR_NIVEL if hasattr(s, 'VIDA_POR_NIVEL') else [0, 5, 6, 8, 9, 10]

def _rotate_vector(x, y, angle_degrees):
    rad = math.radians(angle_degrees); cos_a = math.cos(rad); sin_a = math.sin(rad)
    return x * cos_a - y * sin_a, x * sin_a + y * cos_a

def _move_angle_smooth(current, target, step):
    """ Rotaciona 'current' em direção a 'target' no máximo 'step' graus. """
    diff = (target - current + 180) % 360 - 180
    if abs(diff) < step:
        return target
    return (current + math.copysign(step, diff)) % 360

def calc_hit_angle_rad(target_x, target_y, attacker_x, attacker_y):
    dx = attacker_x - target_x; dy = attacker_y - target_y
    if dx == 0 and dy == 0: return 0
    return math.atan2(dy, dx)

def server_calcular_posicao_spawn(pos_referencia_lista, map_width, map_height):
    margem = 100; dist_min_sq = 600**2
    for _ in range(20):
        x = random.uniform(margem, map_width - margem); y = random.uniform(margem, map_height - margem)
        longe = True
        if pos_referencia_lista:
            for px, py in pos_referencia_lista:
                if (x - px)**2 + (y - py)**2 < dist_min_sq: longe = False; break
        if longe: return (float(x), float(y))
    return (float(random.uniform(margem, map_width - margem)), float(random.uniform(margem, map_height - margem)))

def server_ganhar_pontos(player_state, quantidade):
    if quantidade <= 0: return
    player_state['pontos'] += quantidade; player_state['_pontos_acumulados_para_upgrade'] += quantidade
    limiar = player_state.get('_limiar_pontos_atual', 0)
    if limiar <= 0: limiar = PONTOS_LIMIARES_PARA_UPGRADE[0] if PONTOS_LIMIARES_PARA_UPGRADE else 100; player_state['_limiar_pontos_atual'] = limiar
    for _ in range(50):
        if player_state['_pontos_acumulados_para_upgrade'] < player_state['_limiar_pontos_atual']: break
        player_state['pontos_upgrade_disponiveis'] += 1; player_state['_pontos_acumulados_para_upgrade'] -= player_state['_limiar_pontos_atual']
        pontos_totais = player_state['pontos']; indice = player_state.get('_indice_limiar', 0)
        if indice < len(PONTOS_SCORE_PARA_MUDAR_LIMIAR):
            if pontos_totais >= PONTOS_SCORE_PARA_MUDAR_LIMIAR[indice]:
                player_state['_indice_limiar'] = indice + 1
                if player_state['_indice_limiar'] < len(PONTOS_LIMIARES_PARA_UPGRADE): player_state['_limiar_pontos_atual'] = PONTOS_LIMIARES_PARA_UPGRADE[player_state['_indice_limiar']]

def server_comprar_upgrade(player_state, tipo_upgrade):
    if not tipo_upgrade: return
    is_pvp = player_state.get('is_pvp', False); limite_total = pvp_s.PONTOS_ATRIBUTOS_INICIAIS if is_pvp else MAX_TOTAL_UPGRADES
    if player_state['pontos_upgrade_disponiveis'] <= 0: return
    def pode_comprar(custo_em_slots): return (player_state['total_upgrades_feitos'] + custo_em_slots) <= limite_total
    custo_padrao = 1
    if tipo_upgrade == "motor":
        if player_state['nivel_motor'] < MAX_NIVEL_MOTOR and pode_comprar(custo_padrao):
            player_state['pontos_upgrade_disponiveis'] -= custo_padrao; player_state['total_upgrades_feitos'] += custo_padrao; player_state['nivel_motor'] += 1
    elif tipo_upgrade == "dano":
        if player_state['nivel_dano'] < MAX_NIVEL_DANO and pode_comprar(custo_padrao):
            player_state['pontos_upgrade_disponiveis'] -= custo_padrao; player_state['total_upgrades_feitos'] += custo_padrao; player_state['nivel_dano'] += 1
    elif tipo_upgrade == "auxiliar":
        num = player_state['nivel_aux']
        if num < MAX_AUXILIARES:
            custo_aux = CUSTOS_AUXILIARES[num] if num < len(CUSTOS_AUXILIARES) else 1
            if player_state['pontos_upgrade_disponiveis'] >= custo_aux and pode_comprar(custo_aux):
                player_state['pontos_upgrade_disponiveis'] -= custo_aux; player_state['total_upgrades_feitos'] += custo_aux; player_state['nivel_aux'] += 1
    elif tipo_upgrade == "max_health":
        if player_state['nivel_max_vida'] < len(VIDA_POR_NIVEL) - 1 and pode_comprar(custo_padrao):
            player_state['pontos_upgrade_disponiveis'] -= custo_padrao; player_state['total_upgrades_feitos'] += custo_padrao; player_state['nivel_max_vida'] += 1
            nova_vida = float(VIDA_POR_NIVEL[player_state['nivel_max_vida']]); diff = nova_vida - player_state['max_hp']; player_state['max_hp'] = nova_vida; player_state['hp'] += diff
    elif tipo_upgrade == "escudo":
        if player_state['nivel_escudo'] < MAX_NIVEL_ESCUDO and pode_comprar(custo_padrao):
            player_state['pontos_upgrade_disponiveis'] -= custo_padrao; player_state['total_upgrades_feitos'] += custo_padrao; player_state['nivel_escudo'] += 1

def update_player_logic(player_state, lista_alvos_busca, agora_ms, map_width, map_height, dt=1.0):
    if player_state.get('propulsor_ativo', False):
        if agora_ms > player_state.get('fim_propulsor', 0): player_state['propulsor_ativo'] = False
    
    if player_state.get('is_pre_match', False):
        player_state['alvo_mouse'] = None; player_state['teclas'] = {'w': False, 'a': False, 's': False, 'd': False, 'space': False}; return None
    if agora_ms < player_state.get('tempo_fim_congelamento', 0): player_state['alvo_mouse'] = None; return None
    is_lento = agora_ms < player_state.get('tempo_fim_lentidao', 0)
    
    # --- LÓGICA DE MIRA E ROTAÇÃO ---
    target_angle = player_state['angulo'] # Default
    has_target = False

    if player_state['alvo_lock']:
        alvo = None
        for e in lista_alvos_busca:
            if e.get('id', e.get('nome')) == player_state['alvo_lock']: alvo = e; break
        if alvo and alvo.get('propulsor_ativo', False): player_state['alvo_lock'] = None; alvo = None
        if alvo and alvo.get('hp', 0) > 0:
            vec_x = alvo['x'] - player_state['x']; vec_y = alvo['y'] - player_state['y']
            if vec_x**2 + vec_y**2 > MAX_TARGET_LOCK_DISTANCE_SQ: player_state['alvo_lock'] = None
            else: 
                target_angle = (-math.degrees(math.atan2(vec_y, vec_x)) - 90) % 360
                has_target = True
        else: player_state['alvo_lock'] = None
    elif player_state['alvo_mouse']:
        vec_x = player_state['alvo_mouse'][0] - player_state['x']; vec_y = player_state['alvo_mouse'][1] - player_state['y']
        if vec_x**2 + vec_y**2 > 25: 
            target_angle = (-math.degrees(math.atan2(vec_y, vec_x)) - 90) % 360
            has_target = True

    # Aplica Rotação Suave (Validation)
    if has_target:
        rot_step = s.PLAYER_ROTATION_SPEED * dt
        player_state['angulo'] = _move_angle_smooth(player_state['angulo'], target_angle, rot_step)
    elif not player_state['alvo_lock'] and not player_state['alvo_mouse']:
        # Rotação manual (teclas A/D)
        if player_state['teclas']['a']: player_state['angulo'] = (player_state['angulo'] + (5 * dt)) % 360
        if player_state['teclas']['d']: player_state['angulo'] = (player_state['angulo'] - (5 * dt)) % 360
    
    vel = ((4 + player_state['nivel_motor'] * 0.5) * (0.4 if is_lento else 1.0) + 1) * dt
    vx, vy = 0, 0
    rad = math.radians(player_state['angulo'])
    if player_state['teclas']['w']: vx += -math.sin(rad) * vel; vy += -math.cos(rad) * vel
    if player_state['teclas']['s']: vx -= -math.sin(rad) * vel; vy -= -math.cos(rad) * vel
    if player_state['alvo_mouse'] and not (player_state['teclas']['w'] or player_state['teclas']['s']):
        tx, ty = player_state['alvo_mouse']; dx, dy = tx - player_state['x'], ty - player_state['y']; dist = math.sqrt(dx**2 + dy**2)
        if dist > vel: vx, vy = (dx / dist) * vel, (dy / dist) * vel
        else: player_state['x'], player_state['y'] = tx, ty; player_state['alvo_mouse'] = None; vx, vy = 0, 0
    
    player_state['x'] = max(15, min(player_state['x'] + vx, map_width - 15))
    player_state['y'] = max(15, min(player_state['y'] + vy, map_height - 15))
    
    pode_atirar = player_state['teclas']['space'] or player_state['alvo_lock']
    cooldown_ok = (agora_ms - player_state['ultimo_tiro_tempo']) > player_state['cooldown_tiro']
    if pode_atirar and cooldown_ok:
        player_state['ultimo_tiro_tempo'] = agora_ms
        sx = player_state['x'] + (-math.sin(rad) * OFFSET_PONTA_TIRO); sy = player_state['y'] + (-math.cos(rad) * OFFSET_PONTA_TIRO)
        tipo_base = 'player_pvp' if player_state.get('is_pvp') else 'player_pve'
        if player_state['nivel_dano'] >= s.MAX_NIVEL_DANO: tipo_base += '_max'
        vai_acertar = random.random() < s.CHANCE_ACERTO_TIRO
        velocidade_final = VELOCIDADE_PROJETIL_TELE * (1.5 if vai_acertar else 1.0)
        vel_x = -math.sin(rad) * velocidade_final; vel_y = -math.cos(rad) * velocidade_final
        proj = { 'id': f"{player_state['nome']}_{agora_ms}", 'owner_nome': player_state['nome'], 'x': sx, 'y': sy, 'pos_inicial_x': sx, 'pos_inicial_y': sy, 'dano': s.DANO_POR_NIVEL[player_state['nivel_dano']], 'tipo': tipo_base, 'timestamp_criacao': agora_ms, 'acerto_garantido': vai_acertar, 'velocidade_real': velocidade_final, 'vel_x': vel_x, 'vel_y': vel_y }
        if player_state['alvo_lock']: proj['tipo_proj'] = 'teleguiado'; proj['velocidade'] = velocidade_final; proj['alvo_id'] = player_state['alvo_lock']
        else: proj['tipo_proj'] = 'normal'; proj['velocidade'] = 25; proj['vel_x'] = -math.sin(rad) * 25; proj['vel_y'] = -math.cos(rad) * 25
        return proj
    return None

def process_auxiliaries_logic(p, living_targets, agora_ms):
    new_projs = []; nivel_aux = p.get('nivel_aux', 0)
    if nivel_aux <= 0 or not p.get('alvo_lock'): return new_projs
    t_id = p['alvo_lock']; target = None
    for x in living_targets:
        if x.get('id', x.get('nome')) == t_id and x.get('hp', 0) > 0: target = x; break
    if target and target.get('propulsor_ativo', False): return new_projs
    if not target: return new_projs
    if 'aux_cooldowns' not in p: p['aux_cooldowns'] = [0] * 4
    while len(p['aux_cooldowns']) < nivel_aux: p['aux_cooldowns'].append(0)
    for i in range(nivel_aux):
        if agora_ms <= p['aux_cooldowns'][i]: continue
        off_x, off_y = _rotate_vector(AUX_POSICOES[i][0], AUX_POSICOES[i][1], -p['angulo'])
        ax, ay = p['x'] + off_x, p['y'] + off_y
        dist_sq = (ax - target['x'])**2 + (ay - target['y'])**2
        if dist_sq >= AUX_DISTANCIA_TIRO_SQ: continue
        p['aux_cooldowns'][i] = agora_ms + AUX_COOLDOWN_TIRO
        dist = math.sqrt(dist_sq) if dist_sq > 0 else 1
        dir_x = (target['x'] - ax) / dist; dir_y = (target['y'] - ay) / dist
        tipo_aux = 'player_pvp' if p.get('is_pvp') else 'player_pve'
        if p['nivel_dano'] >= s.MAX_NIVEL_DANO: tipo_aux += '_max'
        vai_acertar = random.random() < s.CHANCE_ACERTO_TIRO; velocidade_final = 14 * (1.5 if vai_acertar else 1.0)
        proj = { 'id': f"{p['nome']}_aux{i}_{agora_ms}", 'owner_nome': p['nome'], 'x': ax, 'y': ay, 'pos_inicial_x': ax, 'pos_inicial_y': ay, 'dano': s.DANO_POR_NIVEL[p['nivel_dano']], 'tipo': tipo_aux, 'tipo_proj': 'teleguiado', 'velocidade': velocidade_final, 'alvo_id': t_id, 'timestamp_criacao': agora_ms, 'vel_x': dir_x * velocidade_final, 'vel_y': dir_y * velocidade_final, 'acerto_garantido': vai_acertar, 'velocidade_real': velocidade_final }
        new_projs.append(proj)
    return new_projs

def update_projectile_physics(proj, all_targets, agora_ms, dt=1.0):
    if proj.get('tipo_proj') == 'teleguiado' and not proj.get('acerto_garantido', True):
        proj['x'] += proj.get('vel_x', 0) * dt; proj['y'] += proj.get('vel_y', 0) * dt; return
    if proj.get('tipo_proj') == 'teleguiado' and proj.get('alvo_id'):
        target = None
        for t in all_targets:
            if t.get('id', t.get('nome')) == proj['alvo_id'] and t.get('hp', 0) > 0: target = t; break
        if target and target.get('propulsor_ativo', False): target = None
        if target:
            target_pos = Vector2(target['x'], target['y']); curr_pos = Vector2(proj['x'], proj['y'])
            desired_vec = target_pos - curr_pos; dist = desired_vec.length()
            velocidade = proj.get('velocidade_real', proj.get('velocidade', VELOCIDADE_PROJETIL_TELE)); passo_neste_frame = velocidade * dt
            if dist <= passo_neste_frame: proj['x'] = target['x']; proj['y'] = target['y']; return
            if dist > 0:
                desired_dir = desired_vec.normalize(); new_vel = desired_dir * velocidade
                proj['vel_x'] = new_vel.x; proj['vel_y'] = new_vel.y
                proj['x'] += new_vel.x * dt; proj['y'] += new_vel.y * dt
        else: proj['tipo_proj'] = 'normal'; proj['x'] += proj.get('vel_x', 0) * dt; proj['y'] += proj.get('vel_y', 0) * dt
    else: proj['x'] += proj.get('vel_x', 0) * dt; proj['y'] += proj.get('vel_y', 0) * dt

def update_npc_generic_logic(npc, players_dict, agora_ms, dt=1.0):
    if npc.get('hp', 0) <= 0: return None
    players_pos_lista = [(p['x'], p['y']) for p in players_dict.values() if p.get('hp', 0) > 0 and not p.get('propulsor_ativo', False)]
    if not players_pos_lista: return None
    alvo_pos = None; dist_min_sq = float('inf')
    for p_pos in players_pos_lista:
        dist_sq = (npc['x'] - p_pos[0])**2 + (npc['y'] - p_pos[1])**2
        if dist_sq > NPC_DETECTION_RANGE_SQ: continue
        if dist_sq < dist_min_sq: dist_min_sq = dist_sq; alvo_pos = p_pos
    if not alvo_pos: return None
    vec_x = alvo_pos[0] - npc['x']; vec_y = alvo_pos[1] - npc['y']; dist = math.sqrt(dist_min_sq) if dist_min_sq > 0 else 1
    tipo = npc.get('tipo', 'perseguidor'); velocidade = VELOCIDADE_PERSEGUIDOR
    if tipo == 'rapido': velocidade = 4.0
    elif tipo == 'bomba': velocidade = 3.0
    elif tipo == 'tiro_rapido': velocidade = 1.5
    elif tipo == 'atordoador': velocidade = 1.0
    velocidade *= dt
    if dist_min_sq > DISTANCIA_PARAR_PERSEGUIDOR_SQ or tipo == 'bomba':
        if dist > 0: dir_x = vec_x / dist; dir_y = vec_y / dist; npc['x'] += dir_x * velocidade; npc['y'] += dir_y * velocidade
    radianos = math.atan2(vec_y, vec_x); npc['angulo'] = (-math.degrees(radianos) - 90) % 360
    if tipo == 'bomba':
        # Se chegou perto o suficiente para detonar
        if dist_min_sq <= KAMIKAZE_DIST_DETONACAO_SQ:
            # [CORREÇÃO] Chama a função de dano em área antes de morrer
            server_processar_explosao_kamikaze(npc, players_dict, agora_ms)
            npc['hp'] = 0 # O NPC morre/some
        return None
    if dist_min_sq < DISTANCIA_TIRO_PERSEGUIDOR_SQ:
        cooldown = npc.get('cooldown_tiro', COOLDOWN_TIRO_PERSEGUIDOR)
        if agora_ms - npc.get('ultimo_tiro_tempo', 0) > cooldown:
            npc['ultimo_tiro_tempo'] = agora_ms
            dir_x = vec_x / dist; dir_y = vec_y / dist
            tipo_proj_npc = 'normal'; velocidade_proj = VELOCIDADE_PROJETIL_NPC; alvo_id_proj = None
            if tipo == 'tiro_rapido': velocidade_proj = 22
            elif tipo == 'rapido': velocidade_proj = 12
            elif tipo == 'atordoador':
                tipo_proj_npc = 'teleguiado_lento'; velocidade_proj = VELOCIDADE_PROJ_LENTO; dist_min_alvo = float('inf')
                for p_state in players_dict.values():
                    if p_state.get('hp', 0) <= 0 or p_state.get('propulsor_ativo', False): continue
                    p_dist_sq = (npc['x'] - p_state['x'])**2 + (npc['y'] - p_state['y'])**2
                    if p_dist_sq < dist_min_alvo: dist_min_alvo = p_dist_sq; alvo_id_proj = p_state['nome']
            vai_acertar = random.random() < s.CHANCE_ACERTO_TIRO; angulo_tiro = radianos
            if not vai_acertar: angulo_tiro += random.uniform(-0.5, 0.5)
            if tipo_proj_npc == 'normal': vel_x = math.cos(angulo_tiro) * velocidade_proj; vel_y = math.sin(angulo_tiro) * velocidade_proj
            else:
                if not alvo_id_proj: return None
                if not vai_acertar: vel_x = math.cos(angulo_tiro) * velocidade_proj; vel_y = math.sin(angulo_tiro) * velocidade_proj
                else: vel_x = dir_x * velocidade_proj; vel_y = dir_y * velocidade_proj
            return { 'id': f"{npc['id']}_{agora_ms}", 'owner_nome': npc['id'], 'x': npc['x'], 'y': npc['y'], 'pos_inicial_x': npc['x'], 'pos_inicial_y': npc['y'], 'angulo_rad': angulo_tiro, 'velocidade': velocidade_proj, 'dano': 1, 'tipo': 'npc', 'tipo_proj': tipo_proj_npc, 'vel_x': vel_x, 'vel_y': vel_y, 'alvo_id': alvo_id_proj, 'timestamp_criacao': agora_ms, 'acerto_garantido': vai_acertar }
    return None

def update_mothership_logic(npc, players_dict, agora_ms, room_ref, dt=1.0):
    if npc.get('hp', 0) <= 0: return None
    target_id = npc.get('ia_alvo_retaliacao'); target = None
    if target_id:
        for p in players_dict.values():
            if p.get('nome') == target_id and p.get('hp', 0) > 0 and not p.get('propulsor_ativo', False): target = p; break
        if not target: npc['ia_alvo_retaliacao'] = None; npc['ia_estado'] = 'VAGANDO'
    if target:
        npc['ia_estado'] = 'RETALIANDO'
        dx = target['x'] - npc['x']; dy = target['y'] - npc['y']; dist = math.sqrt(dx**2 + dy**2) if (dx**2 + dy**2) > 0 else 1
        velocidade = 1.0 * dt
        if dist > 700: npc['x'] += (dx / dist) * velocidade; npc['y'] += (dy / dist) * velocidade
        elif dist < 500: npc['x'] -= (dx / dist) * velocidade; npc['y'] -= (dy / dist) * velocidade
        minions_vivos = [m for m in room_ref.npcs if m.get('tipo') == 'minion_mothership' and m.get('owner_id') == npc['id'] and m.get('hp', 0) > 0]
        if len(minions_vivos) < MAX_MINIONS_MOTHERSHIP:
            if agora_ms - npc.get('ia_ultimo_spawn', 0) > 5000:
                npc['ia_ultimo_spawn'] = agora_ms; qtd_para_spawnar = MAX_MINIONS_MOTHERSHIP - len(minions_vivos)
                for i in range(qtd_para_spawnar):
                    idx_real = len(minions_vivos) + i
                    m = server_spawnar_minion_mothership(npc, target_id, idx_real, MAX_MINIONS_MOTHERSHIP, room_ref.next_npc_id)
                    room_ref.npcs.append(m); room_ref.next_npc_id += 1
    else:
        npc['ia_estado'] = 'VAGANDO'; wander_target = npc.get('ia_wander_target')
        if wander_target:
            wx, wy = wander_target; d_sq = (wx - npc['x'])**2 + (wy - npc['y'])**2
            if d_sq < 100**2: npc['ia_wander_target'] = None
            else: d = math.sqrt(d_sq); npc['x'] += ((wx - npc['x']) / d) * 0.5 * dt; npc['y'] += ((wy - npc['y']) / d) * 0.5 * dt
        else: npc['ia_wander_target'] = (random.randint(100, s.MAP_WIDTH - 100), random.randint(100, s.MAP_HEIGHT - 100))
    return None

def update_boss_congelante_logic(npc, players_dict, agora_ms, room_ref, dt=1.0):
    if npc.get('hp', 0) <= 0: return None
    target_id = npc.get('ia_alvo_retaliacao'); target = None
    if target_id:
        for p in players_dict.values():
            if p.get('nome') == target_id and p.get('hp', 0) > 0 and not p.get('propulsor_ativo', False): target = p; break
        if not target: npc['ia_alvo_retaliacao'] = None
    if target:
        dx = target['x'] - npc['x']; dy = target['y'] - npc['y']; dist = math.sqrt(dx**2 + dy**2) + 0.1
        velocidade = 1.8 * dt; npc['x'] += (dx / dist) * velocidade; npc['y'] += (dy / dist) * velocidade
        if agora_ms - npc.get('ia_ultimo_spawn_minion', 0) > COOLDOWN_SPAWN_MINION_CONGELANTE:
            minions = [m for m in room_ref.npcs if m.get('tipo') == 'minion_congelante' and m.get('owner_id') == npc['id'] and m.get('hp', 0) > 0]
            if len(minions) < MAX_MINIONS_CONGELANTE:
                npc['ia_ultimo_spawn_minion'] = agora_ms
                m = server_spawnar_minion_congelante(npc, target['nome'], len(minions), MAX_MINIONS_CONGELANTE, room_ref.next_npc_id)
                room_ref.npcs.append(m); room_ref.next_npc_id += 1
        cooldown_tiro = getattr(s, 'COOLDOWN_TIRO_CONGELANTE', 2000)
        if agora_ms - npc.get('ultimo_tiro_tempo', 0) > cooldown_tiro:
            npc['ultimo_tiro_tempo'] = agora_ms; vel_x = (dx / dist) * VELOCIDADE_PROJ_CONGELANTE; vel_y = (dy / dist) * VELOCIDADE_PROJ_CONGELANTE
            return { 'id': f"{npc['id']}_{agora_ms}", 'owner_nome': npc['id'], 'x': npc['x'], 'y': npc['y'], 'pos_inicial_x': npc['x'], 'pos_inicial_y': npc['y'], 'dano': 1, 'tipo': 'npc', 'tipo_proj': 'congelante', 'vel_x': vel_x, 'vel_y': vel_y, 'velocidade': VELOCIDADE_PROJ_CONGELANTE, 'timestamp_criacao': agora_ms }
    else:
        wander = npc.get('ia_wander_target')
        if not wander or (npc['x'] - wander[0])**2 + (npc['y'] - wander[1])**2 < 100**2: npc['ia_wander_target'] = (random.randint(100, s.MAP_WIDTH - 100), random.randint(100, s.MAP_HEIGHT - 100))
        if npc.get('ia_wander_target'):
            wx, wy = npc['ia_wander_target']; dx, dy = wx - npc['x'], wy - npc['y']; d = math.sqrt(dx**2 + dy**2) + 0.1
            npc['x'] += (dx / d) * 0.8 * dt; npc['y'] += (dy / d) * 0.8 * dt
    return None

def update_minion_logic(npc, players_dict, agora_ms, room_ref, dt=1.0):
    if npc.get('hp', 0) <= 0: return None
    owner = None
    for n in room_ref.npcs:
        if n.get('id') == npc.get('owner_id') and n.get('hp', 0) > 0: owner = n; break
    if not owner: npc['hp'] = 0; return None
    target = None; target_id = owner.get('ia_alvo_retaliacao')
    if target_id:
        for p in players_dict.values():
            if p.get('nome') == target_id and p.get('hp', 0) > 0 and not p.get('propulsor_ativo', False): target = p; break
    npc['ia_angulo_orbita'] = (npc.get('ia_angulo_orbita', 0) + npc.get('ia_vel_orbita', 1) * dt) % 360
    rad = math.radians(npc['ia_angulo_orbita']); raio = npc.get('ia_raio_orbita', 60)
    dest_x = owner['x'] + math.cos(rad) * raio; dest_y = owner['y'] + math.sin(rad) * raio
    if target and npc.get('tipo') == 'minion_congelante':
        d_owner_target = (owner['x'] - target['x'])**2 + (owner['y'] - target['y'])**2
        if d_owner_target < MINION_CONGELANTE_LEASH_RANGE**2:
            d_to_target_sq = (target['x'] - npc['x'])**2 + (target['y'] - npc['y'])**2
            if d_to_target_sq > 150**2: dest_x, dest_y = target['x'], target['y']
    fator_interp = 0.1 * dt; npc['x'] += (dest_x - npc['x']) * fator_interp; npc['y'] += (dest_y - npc['y']) * fator_interp
    if target:
        cooldown = npc.get('cooldown_tiro', COOLDOWN_TIRO_MINION_CONGELANTE)
        if agora_ms - npc.get('ultimo_tiro_tempo', 0) > cooldown:
            d_target = (target['x'] - npc['x'])**2 + (target['y'] - npc['y'])**2
            if d_target < 400**2:
                npc['ultimo_tiro_tempo'] = agora_ms; dx = target['x'] - npc['x']; dy = target['y'] - npc['y']; dist = math.sqrt(dx**2 + dy**2) + 0.1
                vel_x = (dx / dist) * VELOCIDADE_PROJETIL_NPC; vel_y = (dy / dist) * VELOCIDADE_PROJETIL_NPC
                return { 'id': f"{npc['id']}_{agora_ms}", 'owner_nome': npc['id'], 'x': npc['x'], 'y': npc['y'], 'pos_inicial_x': npc['x'], 'pos_inicial_y': npc['y'], 'dano': 1, 'tipo': 'npc', 'tipo_proj': 'normal', 'vel_x': vel_x, 'vel_y': vel_y, 'velocidade': VELOCIDADE_PROJETIL_NPC, 'timestamp_criacao': agora_ms }
    return None

def server_spawnar_inimigo_aleatorio(x, y, npc_id):
    chance = random.random()
    if chance < 0.05: tipo, hp, tamanho, cooldown_tiro, pontos = "bomba", 1, 25, 999999, 3
    elif chance < 0.10: tipo, hp, tamanho, cooldown_tiro, pontos = "tiro_rapido", 10, 30, 1500, 20
    elif chance < 0.15: tipo, hp, tamanho, cooldown_tiro, pontos = "atordoador", 5, 30, 5000, 25
    elif chance < 0.35: tipo, hp, tamanho, cooldown_tiro, pontos = "atirador_rapido", 1, 30, 500, 10
    elif chance < 0.55: tipo, hp, tamanho, cooldown_tiro, pontos = "rapido", 5, 30, 800, 9
    else: tipo, hp, tamanho, cooldown_tiro, pontos = "perseguidor", 3, 30, COOLDOWN_TIRO_PERSEGUIDOR, 5
    return { 'id': npc_id, 'tipo': tipo, 'x': float(x), 'y': float(y), 'angulo': 0.0, 'hp': hp, 'max_hp': hp, 'tamanho': tamanho, 'cooldown_tiro': cooldown_tiro, 'ultimo_tiro_tempo': 0, 'pontos_por_morte': pontos, 'ia_ultimo_hit_tempo': 0 }

def server_spawnar_mothership(x, y, npc_id):
    return { 'id': npc_id, 'tipo': 'mothership', 'x': float(x), 'y': float(y), 'angulo': 0.0, 'hp': 200, 'max_hp': 200, 'tamanho': 80, 'cooldown_tiro': 999999, 'ultimo_tiro_tempo': 0, 'pontos_por_morte': 100, 'ia_estado': 'VAGANDO', 'ia_alvo_retaliacao': None, 'ia_wander_target': None, 'ia_ultimo_spawn': 0 }

def server_spawnar_boss_congelante(x, y, npc_id):
    hp_boss = getattr(s, 'HP_BOSS_CONGELANTE', 150); tamanho_boss = getattr(s, 'TAMANHO_BOSS_CONGELANTE', 70)
    return { 'id': npc_id, 'tipo': 'boss_congelante', 'x': float(x), 'y': float(y), 'angulo': 0.0, 'hp': hp_boss, 'max_hp': hp_boss, 'tamanho': tamanho_boss, 'cooldown_tiro': 2000, 'ultimo_tiro_tempo': 0, 'pontos_por_morte': 80, 'ia_alvo_retaliacao': None, 'ia_wander_target': None, 'ia_ultimo_spawn_minion': 0 }

def server_spawnar_minion_mothership(owner, target_id, index, max_minions, npc_id_num):
    angulo_inicial = (360 / max(max_minions, 1)) * index
    return { 'id': f"minion_ms_{npc_id_num}", 'tipo': 'minion_mothership', 'owner_id': owner['id'], 'x': owner['x'], 'y': owner['y'], 'angulo': 0.0, 'hp': 5, 'max_hp': 5, 'tamanho': 20, 'cooldown_tiro': 800, 'ultimo_tiro_tempo': 0, 'pontos_por_morte': 3, 'ia_angulo_orbita': angulo_inicial, 'ia_vel_orbita': 2, 'ia_raio_orbita': 100 }

def server_spawnar_minion_congelante(owner, target_id, index, max_minions, npc_id_num):
    angulo_inicial = (360 / max(max_minions, 1)) * index
    return { 'id': f"minion_bc_{npc_id_num}", 'tipo': 'minion_congelante', 'owner_id': owner['id'], 'x': owner['x'], 'y': owner['y'], 'angulo': 0.0, 'hp': HP_MINION_CONGELANTE, 'max_hp': HP_MINION_CONGELANTE, 'tamanho': 25, 'cooldown_tiro': COOLDOWN_TIRO_MINION_CONGELANTE, 'ultimo_tiro_tempo': 0, 'pontos_por_morte': PONTOS_MINION_CONGELANTE, 'ia_angulo_orbita': angulo_inicial, 'ia_vel_orbita': 1.5, 'ia_raio_orbita': 80 }

def server_spawnar_obstaculo(pos_referencia_lista, map_width, map_height, npc_id):
    x, y = server_calcular_posicao_spawn(pos_referencia_lista, map_width, map_height)
    raio_min = getattr(s, 'OBSTACULO_RAIO_MIN', 20); raio_max = getattr(s, 'OBSTACULO_RAIO_MAX', 50); pontos_min = getattr(s, 'OBSTACULO_PONTOS_MIN', 1); pontos_max = getattr(s, 'OBSTACULO_PONTOS_MAX', 5)
    raio = random.randint(raio_min, raio_max); raio_norm = max(raio_min, min(raio, raio_max))
    range_r = raio_max - raio_min; range_p = pontos_max - pontos_min
    pct = (raio_norm - raio_min) / range_r if range_r > 0 else 0; pts = int(round(pontos_min + (pct * range_p))); hp_calculado = 0.1
    return { 'id': npc_id, 'tipo': 'obstaculo', 'x': float(x), 'y': float(y), 'raio': raio, 'hp': hp_calculado, 'max_hp': hp_calculado, 'pontos_por_morte': pts }

def server_processar_explosao_kamikaze(npc, players_dict, agora_ms):
    # Pega o dano base das configurações (padrão 30.0 se não achar)
    dano_base = getattr(s, 'KAMIKAZE_DANO', 30.0)
    
    # Usa o raio de explosão ao quadrado (já calculado no início do arquivo: s.KAMIKAZE_RAIO_EXPLOSAO**2)
    raio_sq = KAMIKAZE_RAIO_EXPLOSAO_SQ 
    
    # Verifica cada jogador online
    for p in players_dict.values():
        # Ignora quem já morreu, espectadores ou quem está com propulsor (invencível)
        if p.get('hp', 0) <= 0 or p.get('propulsor_ativo', False) or p.get('is_spectator', False):
            continue

        # Distância do jogador até a bomba
        dist_sq = (p['x'] - npc['x'])**2 + (p['y'] - npc['y'])**2
        
        # Se estiver dentro da área de explosão
        if dist_sq <= raio_sq:
            # Cálculo de redução de dano (igual aos tiros)
            # Ex: Escudo nível 5 reduz o dano consideravelmente
            reducao = min(p['nivel_escudo'] * REDUCAO_DANO_POR_NIVEL, 75) / 100.0
            dano_final = dano_base * (1.0 - reducao)
            
            # Aplica o dano
            p['hp'] -= dano_final
            p['ultimo_hit_tempo'] = agora_ms
            p['esta_regenerando'] = False # Cancela regeneração se estiver ativo
            
            # (Opcional) Print para debug no servidor se quiser ver acontecendo
            # print(f"[EXPLOSAO] Kamikaze acertou {p['nome']} (Dano: {dano_final:.1f})")