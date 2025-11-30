import paho.mqtt.client as mqtt
import json
import random
import time
import hashlib
import sys
from threading import Thread

# ==============================================================================
# CONFIGURAÇÕES GLOBAIS E CONSTANTES
# ==============================================================================

# Endereço do Broker MQTT. 
# Nota: Para entrega final, utilizar 'localhost' caso o broker esteja local.
# O endereço 'broker.emqx.io' é utilizado aqui para fins de teste e demonstração.
BROKER_ADDRESS = "broker.emqx.io" 
BROKER_PORT = 1883

# Parâmetros de Dificuldade e Mineração
MIN_CHALLENGE = 1            
MAX_CHALLENGE = 20           
NONCE_LIMIT = 50000          

# Definição dos Tópicos MQTT (Conforme especificação do projeto)
TOPIC_INIT = "sd/init"
TOPIC_ELECTION = "sd/voting"    
TOPIC_CHALLENGE = "sd/challenge"
TOPIC_SOLUTION = "sd/solution"  
TOPIC_RESULT = "sd/result"      

# Definição dos Estados do Sistema (Máquina de Estados)
STATE_INIT = "Init"
STATE_ELECTION = "Election"
STATE_CHALLENGE = "Challenge"
STATE_RUNNING = "Running"

# Códigos de Status
WINNER_PENDING = -1             
RESULT_INVALID = 0              
RESULT_VALID = 1                

# ==============================================================================
# FUNÇÕES AUXILIARES E CLASSES
# ==============================================================================

def check_solution(challenge, solution_string):
    """
    Verifica a validade de uma solução proposta para o desafio (Proof of Work).
    A validação consiste em conferir se o hash SHA-1 da string inicia com
    uma quantidade de zeros igual ao parâmetro 'challenge'.
    """
    target = '0' * challenge
    hash_value = hashlib.sha1(solution_string.encode('utf-8')).hexdigest()
    return hash_value, hash_value.startswith(target)

class MineradorThread(Thread):
    """
    Thread dedicada à execução do algoritmo de mineração (Brute Force).
    Separa o processamento pesado da lógica de comunicação MQTT para evitar
    bloqueios e desconexões por timeout.
    """
    def __init__(self, participant, transaction_id, challenge):
        Thread.__init__(self)
        self.participant = participant
        self.transaction_id = transaction_id
        self.challenge = challenge
        self.running = True
        print(f"[{self.participant.client_id}] [MINER] Iniciando mineração. Transação: {transaction_id} | Dificuldade: {challenge}")

    def run(self):
        """Executa o loop de busca pelo Nonce (Proof of Work)."""
        nonce = 0 
        while self.running:
            # Formato da solução candidata: "TransactionID:Nonce"
            test_string = f"{self.transaction_id}:{nonce}" 
            hash_result, is_valid = check_solution(self.challenge, test_string)
            
            if is_valid:
                print(f"[{self.participant.client_id}] [MINER] Solução encontrada. Hash: {hash_result}")
                self.participant._publish_solution(self.transaction_id, test_string)
                self.running = False
                break
            
            nonce += 1
            # Pausa estratégica para evitar 100% de uso da CPU (Starvation)
            if nonce % NONCE_LIMIT == 0:
                time.sleep(0.001)

    def stop(self):
        """Interrompe a execução da thread de mineração."""
        self.running = False
        print(f"[{self.participant.client_id}] [MINER] Processo de mineração interrompido.")

class Participante:
    """
    Classe principal que representa um nó no sistema distribuído.
    Gerencia a conexão MQTT, a máquina de estados e a lógica de eleição/controle.
    """
    def __init__(self, broker, port, n_participants):
        self.broker_address = broker
        self.port = port
        self.N_participants = n_participants
        self.expected_others = n_participants - 1 
        
        # Atributos de Identificação e Estado
        self.client_id = None 
        self.state = STATE_INIT
        self.is_leader = False
        self.leader_id = -1
        self.current_transaction_id = 0
        
        # Estruturas de Dados em Memória
        self.known_participants = set()       
        self.election_votes = {}              
        self.transactions_table = {}          
        self.active_miner = None              
        
        # Configuração do Cliente MQTT com ID único aleatório
        paho_client_id = f"NodeClient_{random.randint(10000, 99999)}"
        self.mqtt_client = self._setup_mqtt_client(paho_client_id)

    def _setup_mqtt_client(self, paho_client_id):
        """Configura a instância do cliente MQTT com callbacks e protocolo v3.1.1."""
        client = mqtt.Client(client_id=paho_client_id, protocol=mqtt.MQTTv311)
        client.on_connect = self.on_connect
        client.on_message = self.on_message
        return client

    def start(self):
        """Inicia o ciclo de vida do nó participante."""
        print(f"--- Sistema Iniciado. Aguardando {self.N_participants} participantes ---")
        try:
            self.mqtt_client.connect(self.broker_address, self.port, 60)
            self.mqtt_client.loop_start() 
            
            # Loop Principal: Gerenciamento de Estados
            while True: 
                if self.state == STATE_INIT:
                    self._republish_init_message()
                elif self.state == STATE_ELECTION:
                    self._republish_election_message()
                
                # Aguarda eventos assíncronos (Callbacks MQTT)
                time.sleep(2) 

        except Exception as e:
            print(f"[ERRO CRÍTICO] Falha na execução: {e}")
            self.mqtt_client.loop_stop()

    # --- MÉTODOS DE COMUNICAÇÃO (PUBLISH) ---
    def _publish(self, topic, data):
        """Método utilitário para publicar mensagens em formato JSON."""
        payload = json.dumps(data)
        self.mqtt_client.publish(topic, payload)
        
    def _publish_challenge(self, transaction_id, challenge):
        msg = {"TransactionID": transaction_id, "Challenge": challenge}
        self._publish(TOPIC_CHALLENGE, msg)

    def _publish_solution(self, transaction_id, solution):
        msg = {"ClientID": self.client_id, "TransactionID": transaction_id, "Solution": solution}
        self._publish(TOPIC_SOLUTION, msg)

    def _publish_result(self, winner_id, transaction_id, solution, result):
        msg = {"ClientID": winner_id, "TransactionID": transaction_id, "Solution": solution, "Result": result}
        self._publish(TOPIC_RESULT, msg)

    # --- CALLBACKS MQTT (EVENT HANDLERS) ---
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[SISTEMA] Conexão com Broker estabelecida. Iniciando fase {STATE_INIT}.")
            # Subscrição em todos os tópicos relevantes
            topics = [(TOPIC_INIT, 0), (TOPIC_ELECTION, 0), (TOPIC_CHALLENGE, 0), (TOPIC_SOLUTION, 0), (TOPIC_RESULT, 0)]
            self.mqtt_client.subscribe(topics)
            self.run_init_state() 
        else:
            print(f"[ERRO] Falha na conexão MQTT. Código de retorno: {rc}")

    def on_message(self, client, userdata, msg):
        """Roteador de mensagens recebidas (Message Dispatcher)."""
        try:
            data = json.loads(msg.payload.decode('utf-8'))
            
            if msg.topic == TOPIC_INIT:
                self._handle_init_message(data)
            elif msg.topic == TOPIC_ELECTION:
                self._handle_election_message(data)
            elif msg.topic == TOPIC_CHALLENGE:
                self._handle_challenge_message_miner(data)
            elif msg.topic == TOPIC_SOLUTION and self.is_leader: 
                self._handle_solution_message_controller(data)
            elif msg.topic == TOPIC_RESULT: 
                self._handle_result_message_miner(data)
                
        except json.JSONDecodeError:
            print(f"[{self.client_id}] [ERRO] Formato de mensagem inválido (Não é JSON).")
        except Exception as e:
            print(f"[{self.client_id}] [ERRO] Exceção no processamento: {e}")
            
    # --- ESTADO I: INICIALIZAÇÃO ---
    def run_init_state(self):
        self.state = STATE_INIT
        if self.client_id is None:
            self.client_id = random.randint(0, 65535)
            print(f"[INIT] Identificador Local (ClientID) gerado: {self.client_id}")
            self.known_participants.add(self.client_id) 
        
    def _republish_init_message(self):
        """Reenvia periodicamente a mensagem de presença até a sincronização."""
        if self.state == STATE_INIT:
            msg = {"ClientID": self.client_id}
            self._publish(TOPIC_INIT, msg)
            print(f"[INIT] Aguardando pares... Sincronizados: {len(self.known_participants)}/{self.N_participants}")
        
    def _handle_init_message(self, data):
        if self.state != STATE_INIT: return
        received_id = data.get("ClientID")
        
        if received_id is None: return
        
        if received_id not in self.known_participants:
            self.known_participants.add(received_id)
            print(f"[{self.client_id}] Novo participante detectado: {received_id}.")
        
        # Verifica critério de transição de estado (Sincronização completa)
        if len(self.known_participants) >= self.N_participants:
            print(f"\n[INIT] Sincronização concluída. Iniciando fase de Eleição.")
            
            # Envia confirmações adicionais para garantir consistência na rede
            for _ in range(3):
                self._publish(TOPIC_INIT, {"ClientID": self.client_id})
                time.sleep(0.2)
                
            self.run_election_state()

    # --- ESTADO II: ELEIÇÃO ---
    def run_election_state(self):
        self.state = STATE_ELECTION
        print(f"\n[{self.client_id}] [ELECTION] Estado de Eleição iniciado.")
        self.election_votes = {} 
        
    def _republish_election_message(self):
        if self.state == STATE_ELECTION:
            # Gera voto local caso não exista
            if self.client_id not in self.election_votes:
                 vote_id = random.randint(0, 65535)
                 self.election_votes[self.client_id] = vote_id
            
            vote_id = self.election_votes.get(self.client_id)
            msg = {"ClientID": self.client_id, "VoteID": vote_id}
            self._publish(TOPIC_ELECTION, msg)

    def _handle_election_message(self, data):
        if self.state != STATE_ELECTION: return 

        received_client_id = data.get("ClientID")
        received_vote_id = data.get("VoteID")
        
        if received_client_id is None or received_vote_id is None: return

        if received_client_id not in self.election_votes:
            self.election_votes[received_client_id] = received_vote_id
            print(f"[{self.client_id}] Voto registrado de {received_client_id}. Computados: {len(self.election_votes)}/{self.N_participants}")

        # Verifica se todos os votos foram coletados
        if len(self.election_votes) >= self.N_participants:
            print(f"\n[ELECTION] Votação encerrada. Apurando resultados...")
            self._elect_leader()
            
    def _elect_leader(self):
        """
        Algoritmo de Eleição:
        Critério Primário: Maior VoteID.
        Critério de Desempate: Maior ClientID.
        """
        current_leader_criteria = (-1, -1) 
        leader_id = -1
        
        for client_id, vote_id in self.election_votes.items():
            criteria = (vote_id, client_id)
            if criteria > current_leader_criteria:
                current_leader_criteria = criteria
                leader_id = client_id
                
        self.leader_id = leader_id
        self.is_leader = (self.client_id == self.leader_id)
        
        papel = 'CONTROLADOR' if self.is_leader else 'MINERADOR'
        print(f"[{self.client_id}] [ELECTION] Resultado: Líder {self.leader_id}. Papel assumido: {papel}.")
        self.run_challenge_state() 
        
    # --- ESTADO III & IV: OPERAÇÃO (CONTROLADOR/MINERADOR) ---
    def _update_transaction_table(self, tx_id, challenge, solution, winner):
        """Atualiza a tabela local de transações (Ledger)."""
        self.transactions_table[tx_id] = {
            'Challenge': challenge,
            'Solution': solution,
            'Winner': winner
        }

    def _generate_next_challenge(self):
        """Lógica do Controlador: Gera e publica novos desafios."""
        self.current_transaction_id += 1
        new_tx_id = self.current_transaction_id
        
        # Define dificuldade (Para demonstração: 1 a 5. Em produção: até 20)
        challenge_value = random.randint(1, 5) 
        
        self._update_transaction_table(new_tx_id, challenge_value, "", WINNER_PENDING)
        print(f"\n[CONTROLADOR] Publicando novo desafio. ID: T{new_tx_id} | Dificuldade: {challenge_value}")
        self._publish_challenge(new_tx_id, challenge_value)

    def run_challenge_state(self):
        self.state = STATE_RUNNING 

        if self.is_leader:
            # Controlador inicia o ciclo de transações
            self.current_transaction_id = -1 
            time.sleep(2) # Aguarda estabilização da rede
            self._generate_next_challenge() 
        else:
            print(f"[{self.client_id}] [MINER] Aguardando desafios do Controlador...")

    # --- LÓGICA DO CONTROLADOR ---
    def _handle_solution_message_controller(self, data):
        """Processa e valida soluções submetidas pelos mineradores."""
        client_id = data.get("ClientID")
        transaction_id = data.get("TransactionID")
        solution = data.get("Solution")
        
        if transaction_id not in self.transactions_table:
            return
            
        current_tx = self.transactions_table[transaction_id]
        
        # Ignora se a transação já foi resolvida
        if current_tx['Winner'] != WINNER_PENDING:
            return
            
        # Validação do Hash SHA-1
        hash_value, is_valid = check_solution(current_tx['Challenge'], solution)
        
        if is_valid:
            print(f"[{self.client_id}] [CONTROLADOR] Solução VÁLIDA recebida de {client_id}.")
            self._update_transaction_table(transaction_id, current_tx['Challenge'], solution, client_id)
            self._publish_result(client_id, transaction_id, solution, RESULT_VALID)
            
            # Agenda o próximo desafio
            time.sleep(2)
            self._generate_next_challenge()
        else:
            print(f"[{self.client_id}] [CONTROLADOR] Solução INVÁLIDA recebida de {client_id}.")
            self._publish_result(client_id, transaction_id, solution, RESULT_INVALID)

    # --- LÓGICA DO MINERADOR ---
    def _handle_challenge_message_miner(self, data):
        """Recebe novo desafio e instancia a thread de mineração."""
        if self.is_leader: return 
        
        transaction_id = data.get("TransactionID")
        challenge = data.get("Challenge")
        
        print(f"[{self.client_id}] [MINER] Desafio recebido: T{transaction_id} (Dificuldade: {challenge})")
        
        # Interrompe mineração anterior se ainda estiver ativa
        if self.active_miner and self.active_miner.is_alive():
            self.active_miner.stop()
            
        self._update_transaction_table(transaction_id, challenge, "", WINNER_PENDING)
        
        # Inicia Thread de Mineração (Non-blocking)
        self.active_miner = MineradorThread(self, transaction_id, challenge)
        self.active_miner.start()
            
    def _handle_result_message_miner(self, data):
        """Recebe o resultado da validação do Controlador."""
        transaction_id = data.get("TransactionID")
        result = data.get("Result") 
        winner_id = data.get("ClientID")

        if transaction_id in self.transactions_table and result == RESULT_VALID:
            print(f"[{self.client_id}] [INFO] Transação T{transaction_id} finalizada. Vencedor: {winner_id}.")
            self.transactions_table[transaction_id]['Winner'] = winner_id
            
            # Se este nó estava minerando a transação vencida por outro, interrompe o trabalho
            if self.active_miner and self.active_miner.transaction_id == transaction_id:
                self.active_miner.stop()

# ==============================================================================
# EXECUÇÃO PRINCIPAL (MAIN)
# ==============================================================================
if __name__ == "__main__":
    # Valor padrão de participantes caso não seja informado via argumento
    qtd_participantes = 3
    
    # Tratamento de argumentos da linha de comando
    if len(sys.argv) > 1:
        try:
            qtd_participantes = int(sys.argv[1])
            print(f"Configuração definida via argumento: {qtd_participantes} participantes.")
        except ValueError:
            print("Argumento inválido. Utilizando configuração padrão (3 participantes).")
    
    # Instanciação e início do nó participante
    participante = Participante(BROKER_ADDRESS, BROKER_PORT, qtd_participantes)
    participante.start()