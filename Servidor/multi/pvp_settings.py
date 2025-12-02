# multi/pvp_settings.py
import pygame
import settings as s # Importa as configs principais para as fontes

# --- Configurações da Partida ---
MAP_WIDTH = 1500
MAP_HEIGHT = 1500
MAX_JOGADORES_PVP = 4
PONTOS_ATRIBUTOS_INICIAIS = 10
PVP_LOBBY_COUNTDOWN_SEGUNDOS = 30 # Contagem regressiva do lobby
PVP_PARTIDA_DURACAO_SEGUNDOS = 180 # 3 minutos (3 * 60)

# --- Posições de Spawn (Cantos) ---
MARGEM_CANTO = 100
SPAWN_POSICOES = [
    # Canto Superior Esquerdo
    pygame.math.Vector2(MARGEM_CANTO, MARGEM_CANTO), 
    # Canto Superior Direito
    pygame.math.Vector2(MAP_WIDTH - MARGEM_CANTO, MARGEM_CANTO), 
    # Canto Inferior Esquerdo
    pygame.math.Vector2(MARGEM_CANTO, MAP_HEIGHT - MARGEM_CANTO), 
    # Canto Inferior Direito
    pygame.math.Vector2(MAP_WIDTH - MARGEM_CANTO, MAP_HEIGHT - MARGEM_CANTO) 
]

# --- Posição do Lobby (Centro) ---
SPAWN_LOBBY = pygame.math.Vector2(MAP_WIDTH / 2, MAP_HEIGHT / 2)

# --- Constantes PVE (Para restauração) ---
# Guarda os valores originais do PVE
PVE_MAP_WIDTH = s.MAP_WIDTH
PVE_MAP_HEIGHT = s.MAP_HEIGHT

# --- Cores da UI do PVP ---
BRANCO = (255, 255, 255)
AMARELO = (255, 255, 0)
VERMELHO = (255, 0, 0)
VERDE = (0, 255, 0)

# --- Fontes (usadas pelo renderer) ---
FONT_TITULO_PVP = s.FONT_TITULO
FONT_TIMER_PVP = s.FONT_TITULO
FONT_VENCEDOR_PVP = s.FONT_TITULO