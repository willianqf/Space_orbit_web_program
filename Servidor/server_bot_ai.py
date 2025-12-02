# server_bot_ai.py
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
BOT_HP_FUGIR_PERC = 0.20 # 20%
BOT_HP_REGENERAR_PERC = 0.50 # 50%
BOT_WANDER_TURN_CHANCE = 0.01 
BOT_WANDER_TURN_DURATION_TICKS = 90 
COOLDOWN_TIRO = 250 # ms

class ServerBotManager:
    def __init__(self, settings, state_globals, logic_callbacks):
        """
        Inicializa o gerenciador de IA dos bots.
        """
        self.s = settings
        
        # Referências de estado global
        self.player_states = state_globals['player_states'] # <-- Aponta para pve_player_states
        self.network_npcs = state_globals['network_npcs']
        
        # Funções "emprestadas" do server.py para evitar import circular
        self.spawn_calculator = logic_callbacks['spawn_calculator']
        self.upgrade_purchaser = logic_callbacks['upgrade_purchaser']

    
    def manage_bot_population(self, max_bots_desejados):
        """
        Verifica bots mortos para remover e ajusta a população (spawna ou remove)
        para atingir max_bots_desejados.
        """
        bots_atuais_keys = []
        bots_para_remover = []

        # 1. Identifica bots existentes e mortos
        for player_key, p_state in list(self.player_states.items()):
            if p_state.get('is_bot', False):
                if p_state.get('hp', 0) <= 0: 
                    bots_para_remover.append(player_key)
                else:
                    bots_atuais_keys.append(player_key)
        
        # 2. Remove bots mortos da lista de contagem
        for k in bots_para_remover:
            if k in bots_atuais_keys: bots_atuais_keys.remove(k)

        # 3. Lógica de Balanceamento (Novo)
        qtd_atual = len(bots_atuais_keys)
        
        # Se tiver MENOS bots do que o desejado -> Spawna
        if qtd_atual < max_bots_desejados:
            diff = max_bots_desejados - qtd_atual
            for _ in range(diff):
                self.spawn_bot()
        
        # Se tiver MAIS bots do que o desejado -> Remove os excedentes
        elif qtd_atual > max_bots_desejados:
            diff = qtd_atual - max_bots_desejados
            # Remove os últimos da lista (FIFO ou LIFO tanto faz aqui)
            for i in range(diff):
                key_to_remove = bots_atuais_keys[i]
                bots_para_remover.append(key_to_remove)
                print(f"[IA] Removendo bot excedente: {key_to_remove} (Sala cheia)")
        
        # Limpeza de NPCs mortos (já existente)
        npcs_antes = len(self.network_npcs)
        self.network_npcs[:] = [n for n in self.network_npcs if n.get('hp', 0) > 0]
        
        return bots_para_remover

    def spawn_bot(self):
        """ Cria um novo bot e o adiciona ao player_states. """
        
        nome_bot = ""
        nomes_existentes = [p['nome'] for p in self.player_states.values()]
        i = 1
        while True:
            nome_bot = f"Bot_{i}"
            if nome_bot not in nomes_existentes:
                break
            i += 1
            if i > 99: 
                print("[LOG] [ERRO] Não foi possível encontrar um nome único para o bot.")
                return

        posicoes_atuais = [(p['x'], p['y']) for p in self.player_states.values()]
        
        # --- INÍCIO: CORREÇÃO DO ERRO (TypeError) ---
        # Passa as dimensões do mapa PVE (self.s) para o spawn_calculator
        spawn_x, spawn_y = self.spawn_calculator(posicoes_atuais, self.s.MAP_WIDTH, self.s.MAP_HEIGHT)
        # --- FIM: CORREÇÃO DO ERRO ---

        nivel_max_vida_inicial = 1
        max_hp_inicial = VIDA_POR_NIVEL[nivel_max_vida_inicial]
        
        bot_state = {
            'nome': nome_bot,
            'is_bot': True,
            'is_pvp': False, # <-- Bot PVE
            'handshake_completo': True, 
            'conn': None, 
            'x': float(spawn_x), 
            'y': float(spawn_y), 
            'angulo': 0.0,
            'max_hp': float(max_hp_inicial), 
            'hp': float(max_hp_inicial), 
            'pontos': 0, 
            'invencivel': False,
            'teclas': { 'w': False, 'a': False, 's': False, 'd': False, 'space': False },
            'alvo_mouse': None, 
            'alvo_lock': None, 
            'ultimo_tiro_tempo': 0, 
            'cooldown_tiro': COOLDOWN_TIRO, 
            'esta_regenerando': False,
            'ultimo_tick_regeneracao': 0,
            'ultimo_hit_tempo': 0,
            'pontos_upgrade_disponiveis': 0,
            'total_upgrades_feitos': 0,
            '_pontos_acumulados_para_upgrade': 0,
            '_limiar_pontos_atual': PONTOS_LIMIARES_PARA_UPGRADE[0],
            '_indice_limiar': 0,
            'nivel_motor': 1,
            'nivel_dano': 1,
            'nivel_max_vida': nivel_max_vida_inicial,
            'nivel_escudo': 0,
            'nivel_aux': 0,
            'aux_cooldowns': [0, 0, 0, 0],
            'bot_estado_ia': "VAGANDO",
            'bot_frames_sem_movimento': 0,
            'bot_posicao_anterior': (0,0),
            'bot_wander_target': None, 
            'tempo_fim_lentidao': 0,
            'tempo_fim_congelamento': 0,
            'bot_last_attacker_id': None, 
            'bot_direcao_orbita': 1, 
            'bot_timer_troca_orbita': 0,
            'bot_duracao_orbita_atual': random.randint(120, 300),
            'bot_flee_destination': None 
        }
        
        self.player_states[nome_bot] = bot_state # Adiciona ao pve_player_states
        print(f"[LOG] [SERVIDOR] Bot {nome_bot} spawnou em ({int(spawn_x)}, {int(spawn_y)}).")
        
    def process_bot_logic(self, bot_state, all_living_players, agora_ms):
        """ Função principal chamada pelo game_loop para fazer um bot pensar. """
        
        if agora_ms < bot_state.get('tempo_fim_congelamento', 0):
            bot_state['teclas'] = { 'w': False, 'a': False, 's': False, 'd': False, 'space': False }
            bot_state['alvo_mouse'] = None
            return

        self._update_ia_decision(bot_state, all_living_players, agora_ms)
        self._process_upgrades(bot_state)
        self._process_regeneration(bot_state, agora_ms)

    def _process_upgrades(self, bot_state):
        """ IA simples para comprar upgrades (de ships.py/NaveBot). """
        if bot_state['pontos_upgrade_disponiveis'] > 0 and bot_state['total_upgrades_feitos'] < MAX_TOTAL_UPGRADES:
            if bot_state['nivel_motor'] < MAX_NIVEL_MOTOR:
                 self.upgrade_purchaser(bot_state, "motor")
            elif bot_state['nivel_escudo'] < MAX_NIVEL_ESCUDO: 
                 self.upgrade_purchaser(bot_state, "escudo")
            elif bot_state['nivel_dano'] < MAX_NIVEL_DANO:
                 self.upgrade_purchaser(bot_state, "dano")
            elif bot_state['nivel_max_vida'] < len(VIDA_POR_NIVEL) - 1:
                 self.upgrade_purchaser(bot_state, "max_health")

    def _process_regeneration(self, bot_state, agora_ms):
        """ Controla a regeneração do Bot, baseado no estado da IA. """
        
        estado_ia = bot_state.get('bot_estado_ia')

        if estado_ia == "FUGINDO":
            bot_state['esta_regenerando'] = False
            return

        esta_parado = (bot_state['alvo_mouse'] is None and not bot_state['teclas']['w'])
        precisa_curar = (bot_state['hp'] < bot_state['max_hp'])
        
        if precisa_curar and esta_parado and not bot_state['esta_regenerando']:
            bot_state['esta_regenerando'] = True
            bot_state['ultimo_tick_regeneracao'] = agora_ms

        elif bot_state['esta_regenerando']:
            if not precisa_curar:
                bot_state['hp'] = bot_state['max_hp']
                bot_state['esta_regenerando'] = False
                if estado_ia == "REGENERANDO_NA_BORDA":
                    bot_state['bot_estado_ia'] = "VAGANDO"
            elif not esta_parado:
                bot_state['esta_regenerando'] = False

    def _update_ia_decision(self, bot_state, all_living_players, agora_ms):
        """ O "Cérebro" do Bot. Decide o que fazer (define 'teclas', 'alvo_mouse', 'alvo_lock'). """
        
        if agora_ms < bot_state.get('tempo_fim_congelamento', 0):
            bot_state['teclas'] = { 'w': False, 'a': False, 's': False, 'd': False, 'space': False }
            bot_state['alvo_mouse'] = None
            return

        if bot_state['alvo_lock']:
            alvo_id_lock = bot_state['alvo_lock']
            alvo_ainda_valido = False
            
            npc_alvo = next((npc for npc in self.network_npcs if npc['id'] == alvo_id_lock and npc.get('hp', 0) > 0), None)
            if npc_alvo:
                alvo_ainda_valido = True
            else:
                player_alvo = next((p for p in all_living_players if p['nome'] == alvo_id_lock and p['nome'] != bot_state['nome'] and p.get('hp', 0) > 0), None)
                if player_alvo:
                    alvo_ainda_valido = True

            if not alvo_ainda_valido:
                bot_state['alvo_lock'] = None
        
        bot_state['teclas']['w'] = False
        bot_state['teclas']['a'] = False
        bot_state['teclas']['s'] = False
        bot_state['teclas']['d'] = False
        bot_state['teclas']['space'] = False
        bot_state['alvo_mouse'] = None
        
        hp_limite_fugir = bot_state['max_hp'] * BOT_HP_FUGIR_PERC # 20%
        hp_limite_regen_obrigatorio = bot_state['max_hp'] * 0.80 # 80%
        
        if bot_state['bot_estado_ia'] != "REGENERANDO_NA_BORDA":
            pos_atual = (bot_state['x'], bot_state['y'])
            pos_anterior = bot_state['bot_posicao_anterior']
            dist_sq_movido = (pos_atual[0] - pos_anterior[0])**2 + (pos_atual[1] - pos_anterior[1])**2
            
            if dist_sq_movido < (3**2):
                bot_state['bot_frames_sem_movimento'] += 1
                if bot_state['bot_frames_sem_movimento'] > 60: 
                    bot_state['bot_estado_ia'] = "VAGANDO"
                    bot_state['alvo_lock'] = None
                    bot_state['alvo_mouse'] = None
                    bot_state['bot_wander_target'] = None 
                    bot_state['bot_frames_sem_movimento'] = 0
            else:
                bot_state['bot_frames_sem_movimento'] = 0
            bot_state['bot_posicao_anterior'] = pos_atual
        else:
            bot_state['bot_frames_sem_movimento'] = 0
            bot_state['bot_posicao_anterior'] = (bot_state['x'], bot_state['y'])
        
        if bot_state['bot_estado_ia'] == "REGENERANDO_NA_BORDA":
            if bot_state['hp'] < hp_limite_regen_obrigatorio:
                bot_state['alvo_mouse'] = None 
                bot_state['bot_flee_destination'] = None
                bot_state['alvo_lock'] = self._find_closest_threat_in_range(bot_state, all_living_players, BOT_DISTANCIA_SCAN_INIMIGO_SQ)
                
                if bot_state['alvo_lock']:
                    bot_state['teclas']['space'] = True 
                return 
            else:
                bot_state['bot_estado_ia'] = "VAGANDO"
                bot_state['bot_flee_destination'] = None
                bot_state['alvo_lock'] = None 

        if bot_state['hp'] <= hp_limite_fugir:
            
            zona_perigo = BOT_DIST_BORDA_SEGURA
            em_zona_perigo = (bot_state['x'] < zona_perigo or 
                              bot_state['x'] > self.s.MAP_WIDTH - zona_perigo or
                              bot_state['y'] < zona_perigo or 
                              bot_state['y'] > self.s.MAP_HEIGHT - zona_perigo)

            if em_zona_perigo:
                bot_state['bot_estado_ia'] = "REGENERANDO_NA_BORDA"
                bot_state['alvo_mouse'] = None 
                bot_state['bot_flee_destination'] = None 
            else:
                bot_state['bot_estado_ia'] = "FUGINDO" 
                if bot_state['bot_flee_destination'] is None:
                    bot_state['bot_flee_destination'] = self._find_closest_edge_point(bot_state['x'], bot_state['y'])
                    print(f"[{bot_state['nome']}] HP baixo! Fugindo para {bot_state['bot_flee_destination']}")
                
                if bot_state['bot_flee_destination']:
                    bot_state['alvo_mouse'] = bot_state['bot_flee_destination']

            bot_state['alvo_lock'] = self._find_closest_threat_in_range(bot_state, all_living_players, BOT_DISTANCIA_SCAN_INIMIGO_SQ)
            
            if bot_state['alvo_lock']:
                bot_state['teclas']['space'] = True 
            
            return 
            
        if bot_state['bot_estado_ia'] == "FUGINDO":
            bot_state['bot_estado_ia'] = "VAGANDO"
            bot_state['bot_flee_destination'] = None
            bot_state['alvo_lock'] = None 

        if bot_state['bot_estado_ia'] in ["VAGANDO", "CAÇANDO"]:
            novo_alvo_encontrado = self._find_closest_threat_online(bot_state, all_living_players)
            
            if novo_alvo_encontrado:
                if bot_state['alvo_lock'] != novo_alvo_encontrado:
                    bot_state['alvo_lock'] = novo_alvo_encontrado
                bot_state['bot_estado_ia'] = "CAÇANDO"
            else:
                bot_state['alvo_lock'] = None
                bot_state['bot_estado_ia'] = "VAGANDO"

        if bot_state['bot_estado_ia'] == "CAÇANDO" or bot_state['bot_estado_ia'] == "ATACANDO":
            if not bot_state['alvo_lock']:
                bot_state['bot_estado_ia'] = "VAGANDO" 
            else:
                alvo_coords = None
                alvo_vivo = False
                target_id = bot_state['alvo_lock']
                
                alvo_npc = next((npc for npc in self.network_npcs if npc['id'] == target_id and npc['hp'] > 0), None)
                if alvo_npc:
                    alvo_coords = (alvo_npc['x'], alvo_npc['y']); alvo_vivo = True
                else:
                    alvo_player = next((p for p in all_living_players if p['nome'] == target_id), None)
                    if alvo_player:
                        alvo_coords = (alvo_player['x'], alvo_player['y']); alvo_vivo = True

                if not alvo_vivo or alvo_coords is None:
                    bot_state['alvo_lock'] = None; bot_state['bot_estado_ia'] = "VAGANDO"
                else:
                    alvo_x, alvo_y = alvo_coords
                    vec_x = alvo_x - bot_state['x']; vec_y = alvo_y - bot_state['y']
                    dist_sq_alvo = vec_x**2 + vec_y**2
                    
                    if dist_sq_alvo > BOT_DISTANCIA_SCAN_INIMIGO_SQ:
                        bot_state['bot_estado_ia'] = "CAÇANDO"
                        bot_state['alvo_mouse'] = (alvo_x, alvo_y) 
                    else:
                        bot_state['bot_estado_ia'] = "ATACANDO"
                        ponto_movimento = (bot_state['x'], bot_state['y']) 
                        
                        if dist_sq_alvo > BOT_DISTANCIA_ORBITA_MAX_SQ: 
                            ponto_movimento = (alvo_x, alvo_y)
                        elif dist_sq_alvo < BOT_DISTANCIA_ORBITA_MIN_SQ: 
                            if (vec_x**2 + vec_y**2) > 0:
                                dist = math.sqrt(dist_sq_alvo)
                                ponto_movimento = (bot_state['x'] - (vec_x/dist) * 200, bot_state['y'] - (vec_y/dist) * 200)
                        else: 
                            if (vec_x**2 + vec_y**2) > 0:
                                bot_state['bot_timer_troca_orbita'] += 1
                                if bot_state['bot_timer_troca_orbita'] > bot_state['bot_duracao_orbita_atual']:
                                    bot_state['bot_timer_troca_orbita'] = 0
                                    bot_state['bot_direcao_orbita'] = -bot_state['bot_direcao_orbita'] 
                                    bot_state['bot_duracao_orbita_atual'] = random.randint(120, 300) 
                                
                                vec_orbita = pygame.math.Vector2(vec_x, vec_y).rotate(75 * bot_state['bot_direcao_orbita'])
                                vec_orbita.scale_to_length(200) 
                                ponto_movimento = (bot_state['x'] + vec_orbita.x, bot_state['y'] + vec_orbita.y)

                        bot_state['alvo_mouse'] = ponto_movimento
                        bot_state['teclas']['space'] = True 
                
        if bot_state['bot_estado_ia'] == "VAGANDO":
            if bot_state['hp'] < hp_limite_regen_obrigatorio:
                 bot_state['alvo_mouse'] = None 
            else:
                chegou_perto = False
                wander_target = bot_state.get('bot_wander_target') 
                
                if wander_target:
                    dist_sq = (bot_state['x'] - wander_target[0])**2 + (bot_state['y'] - wander_target[1])**2
                    if dist_sq < 100**2: 
                        chegou_perto = True
                
                if wander_target is None or chegou_perto:
                    map_margin = 100
                    target_x = random.randint(map_margin, self.s.MAP_WIDTH - map_margin)
                    target_y = random.randint(map_margin, self.s.MAP_HEIGHT - map_margin)
                    bot_state['bot_wander_target'] = (target_x, target_y)
                
                bot_state['alvo_mouse'] = bot_state['bot_wander_target']

    def _find_closest_edge_point(self, bot_pos_x, bot_pos_y):
            """
            Calcula o ponto mais próximo na borda do mapa para onde o bot deve fugir.
            Retorna uma tupla (x, y).
            """
            dist_to_top = bot_pos_y
            dist_to_bottom = self.s.MAP_HEIGHT - bot_pos_y
            dist_to_left = bot_pos_x
            dist_to_right = self.s.MAP_WIDTH - bot_pos_x

            min_dist = min(dist_to_top, dist_to_bottom, dist_to_left, dist_to_right)
            
            margin = 50 

            if min_dist == dist_to_top:
                return (bot_pos_x, float(margin))
            elif min_dist == dist_to_bottom:
                return (bot_pos_x, float(self.s.MAP_HEIGHT - margin))
            elif min_dist == dist_to_left:
                return (float(margin), bot_pos_y)
            else: # dist_to_right
                return (float(self.s.MAP_WIDTH - margin), bot_pos_y)
    
    def _find_closest_threat_online(self, bot_state, all_living_players):
        """
        Encontra a ameaça (Inimigo ou Player/Bot) MAIS PRÓXIMA para a IA online.
        PRIORIZA O ATACANTE RECENTE se ele estiver no alcance.
        Retorna o ID da ameaça (str), ou None.
        """
        
        alvo_final_id = None
        dist_min_sq = BOT_DISTANCIA_SCAN_GERAL_SQ 

        attacker_id = bot_state.get('bot_last_attacker_id')
        if attacker_id:
            alvo_atacante_vivo = None
            attacker_npc = next((npc for npc in self.network_npcs if npc['id'] == attacker_id and npc.get('hp', 0) > 0), None)
            if attacker_npc:
                alvo_atacante_vivo = attacker_id
                dist_sq_atacante = (attacker_npc['x'] - bot_state['x'])**2 + (attacker_npc['y'] - bot_state['y'])**2
                if dist_sq_atacante < BOT_DISTANCIA_SCAN_INIMIGO_SQ:
                    return attacker_id 
            else:
                attacker_player = next((p for p in all_living_players if p['nome'] == attacker_id and p.get('hp', 0) > 0), None)
                if attacker_player:
                    alvo_atacante_vivo = attacker_id
                    dist_sq_atacante = (attacker_player['x'] - bot_state['x'])**2 + (attacker_player['y'] - bot_state['y'])**2
                    if dist_sq_atacante < BOT_DISTANCIA_SCAN_INIMIGO_SQ:
                         return attacker_id 
            
            if not alvo_atacante_vivo:
                bot_state['bot_last_attacker_id'] = None

        for npc in self.network_npcs:
            if npc['hp'] <= 0: continue
            dist_sq = (npc['x'] - bot_state['x'])**2 + (npc['y'] - bot_state['y'])**2
            
            if dist_sq < dist_min_sq:
                dist_min_sq = dist_sq       
                alvo_final_id = npc['id'] 

        for player in all_living_players:
            if player['nome'] == bot_state['nome']: continue 
            dist_sq = (player['x'] - bot_state['x'])**2 + (player['y'] - bot_state['y'])**2
            
            if dist_sq < dist_min_sq:
                dist_min_sq = dist_sq         
                alvo_final_id = player['nome'] 
        
        return alvo_final_id
    
    def _find_closest_threat_in_range(self, bot_state, all_living_players, range_sq):
        """
        Encontra a ameaça (Inimigo ou Player/Bot) MAIS PRÓXIMA que está
        DENTRO de um alcance (range_sq) específico.
        Retorna o ID da ameaça (str), ou None.
        """
        alvo_final_id = None
        dist_min_sq = range_sq 

        for npc in self.network_npcs:
            if npc['hp'] <= 0: continue
            dist_sq = (npc['x'] - bot_state['x'])**2 + (npc['y'] - bot_state['y'])**2
            
            if dist_sq < dist_min_sq:
                dist_min_sq = dist_sq       
                alvo_final_id = npc['id'] 

        for player in all_living_players:
            if player['nome'] == bot_state['nome']: continue 
            dist_sq = (player['x'] - bot_state['x'])**2 + (player['y'] - bot_state['y'])**2
            
            if dist_sq < dist_min_sq:
                dist_min_sq = dist_sq         
                alvo_final_id = player['nome'] 
        
        return alvo_final_id