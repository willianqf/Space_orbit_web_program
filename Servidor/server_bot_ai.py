# Servidor/server_bot_ai.py
import random
import math
import pygame # Para Vector2
from settings import (
    PONTOS_LIMIARES_PARA_UPGRADE, MAX_TOTAL_UPGRADES, MAX_NIVEL_MOTOR,
    MAX_NIVEL_ESCUDO, MAX_NIVEL_DANO,
    VIDA_POR_NIVEL
)

# --- CONSTANTES DA IA DO BOT ---
BOT_DISTANCIA_SCAN_GERAL_SQ = 1500**2 
BOT_DISTANCIA_SCAN_INIMIGO_SQ = 600**2
BOT_DISTANCIA_ORBITA_MAX_SQ = 300**2
BOT_DISTANCIA_ORBITA_MIN_SQ = 200**2
BOT_DISTANCIA_TIRO_IA_SQ = 500**2
BOT_DIST_BORDA_SEGURA = 400

# Configurações de Sobrevivência
BOT_HP_FUGIR_PERC = 0.35      # Foge com 35% de vida
BOT_HP_REGENERAR_PERC = 0.70  # Regenera até 70%

BOT_WANDER_TURN_CHANCE = 0.01 
BOT_WANDER_TURN_DURATION_TICKS = 90 
COOLDOWN_TIRO = 250 

class ServerBotManager:
    def __init__(self, settings, state_globals, logic_callbacks):
        self.s = settings
        self.player_states = state_globals['player_states'] 
        self.network_npcs = state_globals['network_npcs']
        self.spawn_calculator = logic_callbacks['spawn_calculator']
        self.upgrade_purchaser = logic_callbacks['upgrade_purchaser']
    
    def manage_bot_population(self, max_bots_desejados):
        bots_atuais_keys = []
        bots_para_remover = []

        for player_key, p_state in list(self.player_states.items()):
            if p_state.get('is_bot', False):
                if p_state.get('hp', 0) <= 0: 
                    bots_para_remover.append(player_key)
                else:
                    bots_atuais_keys.append(player_key)
        
        for k in bots_para_remover:
            if k in bots_atuais_keys: bots_atuais_keys.remove(k)

        qtd_atual = len(bots_atuais_keys)
        
        if qtd_atual < max_bots_desejados:
            diff = max_bots_desejados - qtd_atual
            for _ in range(diff):
                self.spawn_bot()
        elif qtd_atual > max_bots_desejados:
            diff = qtd_atual - max_bots_desejados
            for i in range(diff):
                key_to_remove = bots_atuais_keys[i]
                bots_para_remover.append(key_to_remove)
                print(f"[IA] Removendo bot excedente: {key_to_remove}")
        
        return bots_para_remover

    def spawn_bot(self):
        nomes_base = [
            "Viper", "Rex", "Neo", "Zara", "Orion", "Nova", "Luna", "Titan", 
            "Astro", "Falcon", "Ghost", "Shadow", "Hunter", "Sky", "Draco",
            "Phoenix", "Nebula", "Cosmo", "Ranger", "Pilot", "Stark", "Wolf",
            "Raven", "Blaze", "Storm", "Hawk", "Eagle", "Cobra", "Sonic", 
            "Thunder", "Omega", "Alpha", "Delta", "Echo", "Kilo", "Zulu"
        ]
        
        nomes_existentes = [p['nome'] for p in self.player_states.values()]
        nome_bot = ""
        tentativas = 0
        while True:
            base = random.choice(nomes_base)
            numero = random.randint(100, 9999)
            nome_bot = f"{base}{numero}"
            if nome_bot not in nomes_existentes: break
            tentativas += 1
            if tentativas > 100:
                nome_bot = f"Bot_{random.randint(10000, 99999)}"
                break

        posicoes_atuais = [(p['x'], p['y']) for p in self.player_states.values()]
        spawn_x, spawn_y = self.spawn_calculator(posicoes_atuais, self.s.MAP_WIDTH, self.s.MAP_HEIGHT)

        nivel_max_vida_inicial = 1
        max_hp_inicial = VIDA_POR_NIVEL[nivel_max_vida_inicial]
        
        bot_state = {
            'nome': nome_bot, 'is_bot': True, 'is_pvp': False, 'handshake_completo': True, 'conn': None, 
            'x': float(spawn_x), 'y': float(spawn_y), 'angulo': 0.0,
            'max_hp': float(max_hp_inicial), 'hp': float(max_hp_inicial), 'pontos': 0, 'invencivel': False,
            'teclas': { 'w': False, 'a': False, 's': False, 'd': False, 'space': False },
            'alvo_mouse': None, 'alvo_lock': None, 'ultimo_tiro_tempo': 0, 'cooldown_tiro': COOLDOWN_TIRO, 
            'esta_regenerando': False, 'ultimo_tick_regeneracao': 0, 'ultimo_hit_tempo': 0,
            'pontos_upgrade_disponiveis': 0, 'total_upgrades_feitos': 0,
            '_pontos_acumulados_para_upgrade': 0, '_limiar_pontos_atual': PONTOS_LIMIARES_PARA_UPGRADE[0], '_indice_limiar': 0,
            'nivel_motor': 1, 'nivel_dano': 1, 'nivel_max_vida': nivel_max_vida_inicial, 'nivel_escudo': 0, 'nivel_aux': 0,
            'aux_cooldowns': [0, 0, 0, 0], 'bot_estado_ia': "VAGANDO", 'bot_frames_sem_movimento': 0,
            'bot_posicao_anterior': (0,0), 'bot_wander_target': None, 
            'tempo_fim_lentidao': 0, 'tempo_fim_congelamento': 0, 'bot_last_attacker_id': None, 
            'bot_direcao_orbita': 1, 'bot_timer_troca_orbita': 0, 'bot_duracao_orbita_atual': random.randint(120, 300),
            'bot_flee_destination': None, 'propulsor_ativo': False, 'fim_propulsor': 0, 'cooldown_propulsor': 0
        }
        self.player_states[nome_bot] = bot_state
        print(f"[LOG] [SERVIDOR] {nome_bot} entrou no setor ({int(spawn_x)}, {int(spawn_y)}).")
        
    def process_bot_logic(self, bot_state, all_living_players, agora_ms):
        if agora_ms < bot_state.get('tempo_fim_congelamento', 0):
            bot_state['teclas'] = { 'w': False, 'a': False, 's': False, 'd': False, 'space': False }
            bot_state['alvo_mouse'] = None
            return

        self._update_ia_decision(bot_state, all_living_players, agora_ms)
        self._process_upgrades(bot_state)
        self._process_regeneration(bot_state, agora_ms)

    def _process_upgrades(self, bot_state):
        if bot_state['pontos_upgrade_disponiveis'] > 0 and bot_state['total_upgrades_feitos'] < MAX_TOTAL_UPGRADES:
            if bot_state['nivel_motor'] < MAX_NIVEL_MOTOR: self.upgrade_purchaser(bot_state, "motor")
            elif bot_state['nivel_escudo'] < MAX_NIVEL_ESCUDO: self.upgrade_purchaser(bot_state, "escudo")
            elif bot_state['nivel_dano'] < MAX_NIVEL_DANO: self.upgrade_purchaser(bot_state, "dano")
            elif bot_state['nivel_max_vida'] < len(VIDA_POR_NIVEL) - 1: self.upgrade_purchaser(bot_state, "max_health")

    def _process_regeneration(self, bot_state, agora_ms):
        estado_ia = bot_state.get('bot_estado_ia')
        if estado_ia == "FUGINDO":
            bot_state['esta_regenerando'] = False
            return

        esta_parado = (bot_state['alvo_mouse'] is None and not bot_state['teclas']['w'])
        precisa_curar = (bot_state['hp'] < (bot_state['max_hp'] * BOT_HP_REGENERAR_PERC))
        
        if precisa_curar and esta_parado and not bot_state['esta_regenerando']:
            bot_state['esta_regenerando'] = True
            bot_state['ultimo_tick_regeneracao'] = agora_ms
        elif bot_state['esta_regenerando']:
            if not precisa_curar:
                bot_state['esta_regenerando'] = False
                if estado_ia == "REGENERANDO_NA_BORDA":
                    bot_state['bot_estado_ia'] = "VAGANDO"
            elif not esta_parado:
                bot_state['esta_regenerando'] = False

    def _update_ia_decision(self, bot_state, all_living_players, agora_ms):
        if agora_ms < bot_state.get('tempo_fim_congelamento', 0): return

        self._check_propulsor_usage(bot_state, all_living_players, agora_ms)

        if bot_state['alvo_lock']:
            alvo_id_lock = bot_state['alvo_lock']
            alvo_ainda_valido = False
            npc_alvo = next((npc for npc in self.network_npcs if npc['id'] == alvo_id_lock and npc.get('hp', 0) > 0), None)
            if npc_alvo: alvo_ainda_valido = True
            else:
                player_alvo = next((p for p in all_living_players if p['nome'] == alvo_id_lock and p['nome'] != bot_state['nome'] and p.get('hp', 0) > 0), None)
                if player_alvo:
                    if player_alvo.get('propulsor_ativo', False): alvo_ainda_valido = False
                    else: alvo_ainda_valido = True
            if not alvo_ainda_valido: bot_state['alvo_lock'] = None
        
        bot_state['teclas'] = { 'w': False, 'a': False, 's': False, 'd': False, 'space': False }
        bot_state['alvo_mouse'] = None
        
        hp_limite_fugir = bot_state['max_hp'] * BOT_HP_FUGIR_PERC
        hp_limite_regen_obrigatorio = bot_state['max_hp'] * BOT_HP_REGENERAR_PERC
        
        if bot_state['bot_estado_ia'] != "REGENERANDO_NA_BORDA":
            pos_atual = (bot_state['x'], bot_state['y'])
            pos_anterior = bot_state['bot_posicao_anterior']
            dist_sq_movido = (pos_atual[0] - pos_anterior[0])**2 + (pos_atual[1] - pos_anterior[1])**2
            if dist_sq_movido < (3**2):
                bot_state['bot_frames_sem_movimento'] += 1
                if bot_state['bot_frames_sem_movimento'] > 60: 
                    bot_state['bot_estado_ia'] = "VAGANDO"
                    bot_state['alvo_lock'] = None; bot_state['alvo_mouse'] = None; bot_state['bot_wander_target'] = None 
                    bot_state['bot_frames_sem_movimento'] = 0
            else: bot_state['bot_frames_sem_movimento'] = 0
            bot_state['bot_posicao_anterior'] = pos_atual
        else:
            bot_state['bot_frames_sem_movimento'] = 0
            bot_state['bot_posicao_anterior'] = (bot_state['x'], bot_state['y'])
        
        if bot_state['bot_estado_ia'] == "REGENERANDO_NA_BORDA":
            if bot_state['hp'] < hp_limite_regen_obrigatorio:
                bot_state['alvo_mouse'] = None; bot_state['bot_flee_destination'] = None
                bot_state['alvo_lock'] = self._find_closest_threat_in_range(bot_state, all_living_players, BOT_DISTANCIA_SCAN_INIMIGO_SQ)
                if bot_state['alvo_lock']: bot_state['teclas']['space'] = True 
                return 
            else:
                bot_state['bot_estado_ia'] = "VAGANDO"
                bot_state['bot_flee_destination'] = None; bot_state['alvo_lock'] = None 

        if bot_state['hp'] <= hp_limite_fugir:
            zona_perigo = BOT_DIST_BORDA_SEGURA
            em_zona_perigo = (bot_state['x'] < zona_perigo or bot_state['x'] > self.s.MAP_WIDTH - zona_perigo or bot_state['y'] < zona_perigo or bot_state['y'] > self.s.MAP_HEIGHT - zona_perigo)
            if em_zona_perigo:
                bot_state['bot_estado_ia'] = "REGENERANDO_NA_BORDA"
                bot_state['alvo_mouse'] = None; bot_state['bot_flee_destination'] = None 
            else:
                bot_state['bot_estado_ia'] = "FUGINDO" 
                if bot_state['bot_flee_destination'] is None: bot_state['bot_flee_destination'] = self._find_closest_edge_point(bot_state['x'], bot_state['y'])
                if bot_state['bot_flee_destination']: bot_state['alvo_mouse'] = bot_state['bot_flee_destination']
            bot_state['alvo_lock'] = self._find_closest_threat_in_range(bot_state, all_living_players, BOT_DISTANCIA_SCAN_INIMIGO_SQ)
            if bot_state['alvo_lock']: bot_state['teclas']['space'] = True 
            return 
            
        if bot_state['bot_estado_ia'] == "FUGINDO":
            bot_state['bot_estado_ia'] = "VAGANDO"
            bot_state['bot_flee_destination'] = None; bot_state['alvo_lock'] = None 

        if bot_state['bot_estado_ia'] in ["VAGANDO", "CAÇANDO"]:
            novo_alvo_encontrado = self._find_closest_threat_online(bot_state, all_living_players)
            if novo_alvo_encontrado:
                if bot_state['alvo_lock'] != novo_alvo_encontrado: bot_state['alvo_lock'] = novo_alvo_encontrado
                bot_state['bot_estado_ia'] = "CAÇANDO"
            else:
                bot_state['alvo_lock'] = None; bot_state['bot_estado_ia'] = "VAGANDO"

        if bot_state['bot_estado_ia'] == "CAÇANDO" or bot_state['bot_estado_ia'] == "ATACANDO":
            if not bot_state['alvo_lock']: bot_state['bot_estado_ia'] = "VAGANDO" 
            else:
                alvo_coords = None; alvo_vivo = False; target_id = bot_state['alvo_lock']
                npc_alvo = next((npc for npc in self.network_npcs if npc['id'] == target_id and npc.get('hp', 0) > 0), None)
                if npc_alvo: alvo_coords = (npc_alvo['x'], npc_alvo['y']); alvo_vivo = True
                else:
                    player_alvo = next((p for p in all_living_players if p['nome'] == target_id and p['nome'] != bot_state['nome'] and p.get('hp', 0) > 0), None)
                    if player_alvo:
                        if player_alvo.get('propulsor_ativo', False): alvo_vivo = False
                        else: alvo_coords = (player_alvo['x'], player_alvo['y']); alvo_vivo = True

                if not alvo_vivo or alvo_coords is None: bot_state['alvo_lock'] = None; bot_state['bot_estado_ia'] = "VAGANDO"
                else:
                    alvo_x, alvo_y = alvo_coords
                    vec_x = alvo_x - bot_state['x']; vec_y = alvo_y - bot_state['y']
                    dist_sq_alvo = vec_x**2 + vec_y**2
                    
                    if dist_sq_alvo > BOT_DISTANCIA_SCAN_INIMIGO_SQ:
                        bot_state['bot_estado_ia'] = "CAÇANDO"; bot_state['alvo_mouse'] = (alvo_x, alvo_y) 
                    else:
                        bot_state['bot_estado_ia'] = "ATACANDO"
                        ponto_movimento = (bot_state['x'], bot_state['y']) 
                        if dist_sq_alvo > BOT_DISTANCIA_ORBITA_MAX_SQ: ponto_movimento = (alvo_x, alvo_y)
                        elif dist_sq_alvo < BOT_DISTANCIA_ORBITA_MIN_SQ: 
                            if (vec_x**2 + vec_y**2) > 0:
                                dist = math.sqrt(dist_sq_alvo)
                                ponto_movimento = (bot_state['x'] - (vec_x/dist) * 200, bot_state['y'] - (vec_y/dist) * 200)
                        else: 
                            if (vec_x**2 + vec_y**2) > 0:
                                bot_state['bot_timer_troca_orbita'] += 1
                                if bot_state['bot_timer_troca_orbita'] > bot_state['bot_duracao_orbita_atual']:
                                    bot_state['bot_timer_troca_orbita'] = 0; bot_state['bot_direcao_orbita'] = -bot_state['bot_direcao_orbita'] 
                                    bot_state['bot_duracao_orbita_atual'] = random.randint(120, 300) 
                                vec_orbita = pygame.math.Vector2(vec_x, vec_y).rotate(75 * bot_state['bot_direcao_orbita'])
                                vec_orbita.scale_to_length(200) 
                                ponto_movimento = (bot_state['x'] + vec_orbita.x, bot_state['y'] + vec_orbita.y)
                        bot_state['alvo_mouse'] = ponto_movimento; bot_state['teclas']['space'] = True 
                
        if bot_state['bot_estado_ia'] == "VAGANDO":
            if bot_state['hp'] < hp_limite_regen_obrigatorio: bot_state['alvo_mouse'] = None 
            else:
                chegou_perto = False
                wander_target = bot_state.get('bot_wander_target') 
                if wander_target:
                    dist_sq = (bot_state['x'] - wander_target[0])**2 + (bot_state['y'] - wander_target[1])**2
                    if dist_sq < 100**2: chegou_perto = True
                if wander_target is None or chegou_perto:
                    map_margin = 100
                    target_x = random.randint(map_margin, self.s.MAP_WIDTH - map_margin)
                    target_y = random.randint(map_margin, self.s.MAP_HEIGHT - map_margin)
                    bot_state['bot_wander_target'] = (target_x, target_y)
                bot_state['alvo_mouse'] = bot_state['bot_wander_target']

    def _check_propulsor_usage(self, bot_state, all_living_players, agora_ms):
        if agora_ms < bot_state.get('cooldown_propulsor', 0): return
        hp_perc = bot_state['hp'] / bot_state['max_hp']
        hp_critico = hp_perc < 0.35 
        tomou_dano_recente = (agora_ms - bot_state.get('ultimo_hit_tempo', 0)) < 1000
        ameaca_id = self._find_closest_threat_in_range(bot_state, all_living_players, BOT_DISTANCIA_SCAN_INIMIGO_SQ)
        tem_ameaca = (ameaca_id is not None)
        deve_ativar = tem_ameaca and (hp_critico or tomou_dano_recente)

        if deve_ativar:
            bot_state['propulsor_ativo'] = True
            bot_state['fim_propulsor'] = agora_ms + self.s.DURACAO_PROPULSOR_IMUNE
            bot_state['cooldown_propulsor'] = agora_ms + self.s.COOLDOWN_PROPULSOR
            for p in all_living_players:
                if p.get('alvo_lock') == bot_state['nome']: p['alvo_lock'] = None
            for npc in self.network_npcs:
                if npc.get('ia_alvo_id') == bot_state['nome']: npc['ia_alvo_id'] = None
                if npc.get('ia_alvo_retaliacao') == bot_state['nome']: npc['ia_alvo_retaliacao'] = None

    def _find_closest_edge_point(self, bot_pos_x, bot_pos_y):
            dist_to_top = bot_pos_y
            dist_to_bottom = self.s.MAP_HEIGHT - bot_pos_y
            dist_to_left = bot_pos_x
            dist_to_right = self.s.MAP_WIDTH - bot_pos_x
            min_dist = min(dist_to_top, dist_to_bottom, dist_to_left, dist_to_right)
            margin = 50 
            if min_dist == dist_to_top: return (bot_pos_x, float(margin))
            elif min_dist == dist_to_bottom: return (bot_pos_x, float(self.s.MAP_HEIGHT - margin))
            elif min_dist == dist_to_left: return (float(margin), bot_pos_y)
            else: return (float(self.s.MAP_WIDTH - margin), bot_pos_y)
    
    def _find_closest_threat_online(self, bot_state, all_living_players):
        """ Prioriza NPCs normais aplicando penalidade de distância aos Bosses """
        alvo_final_id = None
        dist_min_sq = BOT_DISTANCIA_SCAN_GERAL_SQ 

        attacker_id = bot_state.get('bot_last_attacker_id')
        if attacker_id:
            alvo_atacante_vivo = None
            attacker_npc = next((npc for npc in self.network_npcs if npc['id'] == attacker_id and npc.get('hp', 0) > 0), None)
            if attacker_npc:
                alvo_atacante_vivo = attacker_id
                dist_sq_atacante = (attacker_npc['x'] - bot_state['x'])**2 + (attacker_npc['y'] - bot_state['y'])**2
                if dist_sq_atacante < BOT_DISTANCIA_SCAN_INIMIGO_SQ: return attacker_id 
            else:
                attacker_player = next((p for p in all_living_players if p['nome'] == attacker_id and p.get('hp', 0) > 0), None)
                if attacker_player:
                    if not attacker_player.get('propulsor_ativo', False):
                        alvo_atacante_vivo = attacker_id
                        dist_sq_atacante = (attacker_player['x'] - bot_state['x'])**2 + (attacker_player['y'] - bot_state['y'])**2
                        if dist_sq_atacante < BOT_DISTANCIA_SCAN_INIMIGO_SQ: return attacker_id 
            if not alvo_atacante_vivo: bot_state['bot_last_attacker_id'] = None

        for npc in self.network_npcs:
            if npc['hp'] <= 0: continue
            if npc['tipo'] == 'obstaculo': continue 
            
            dist_sq = (npc['x'] - bot_state['x'])**2 + (npc['y'] - bot_state['y'])**2
            
            # --- PENALIDADE DE PESO PARA BOSSES ---
            # Faz o Boss parecer 2.5x mais longe, forçando o bot a focar nos minions/npcs normais
            if npc['tipo'] in ['mothership', 'boss_congelante']:
                 dist_sq = dist_sq * 2.5 
            # --------------------------------------

            if dist_sq < dist_min_sq:
                dist_min_sq = dist_sq       
                alvo_final_id = npc['id'] 

        for player in all_living_players:
            if player['nome'] == bot_state['nome']: continue 
            if player.get('propulsor_ativo', False): continue
            
            dist_sq = (player['x'] - bot_state['x'])**2 + (player['y'] - bot_state['y'])**2
            
            if dist_sq < dist_min_sq:
                dist_min_sq = dist_sq         
                alvo_final_id = player['nome'] 
        
        return alvo_final_id
    
    def _find_closest_threat_in_range(self, bot_state, all_living_players, range_sq):
        alvo_final_id = None
        dist_min_sq = range_sq 

        for npc in self.network_npcs:
            if npc['hp'] <= 0: continue
            dist_sq = (npc['x'] - bot_state['x'])**2 + (npc['y'] - bot_state['y'])**2
            
            # --- PENALIDADE DE PESO PARA BOSSES EM CURTA DISTÂNCIA TAMBÉM ---
            if npc['tipo'] in ['mothership', 'boss_congelante']:
                 dist_sq = dist_sq * 2.0
            
            if dist_sq < dist_min_sq:
                dist_min_sq = dist_sq       
                alvo_final_id = npc['id'] 

        for player in all_living_players:
            if player['nome'] == bot_state['nome']: continue 
            if player.get('propulsor_ativo', False): continue
            dist_sq = (player['x'] - bot_state['x'])**2 + (player['y'] - bot_state['y'])**2
            if dist_sq < dist_min_sq:
                dist_min_sq = dist_sq         
                alvo_final_id = player['nome'] 
        
        return alvo_final_id