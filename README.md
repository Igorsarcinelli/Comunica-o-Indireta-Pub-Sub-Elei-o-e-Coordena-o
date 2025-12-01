# Laboratório III – Comunicação Indireta Pub/Sub, Eleição e Coordenação

Este repositório contém a implementação de um sistema distribuído de mineração em Python, utilizando o protocolo **MQTT** (modelo publish/subscribe) para comunicação entre nós, com **eleição de líder** e **coordenação centralizada**.

Cada execução do arquivo `Minerador.py` representa um nó participante conectado a um broker MQTT. Os nós passam pelas fases de **inicialização (INIT)**, **eleição (ELECTION)** e **execução (RUNNING)**, podendo assumir o papel de:

- **CONTROLADOR (líder)** – coordena o sistema, gera desafios e valida soluções;
- **MINERADOR** – recebe desafios e executa a prova-de-trabalho (Proof of Work).

![Video](comunicacaoPub.gif)
---

## 🗂 Estrutura do repositório

- `Minerador.py`  
  Implementação completa do nó participante (MQTT, máquina de estados, eleição e mineração).

- `README.md`  
  Instruções de execução e resumo técnico do projeto.

---

## ✅ Requisitos

- **Python 3** instalado
- Biblioteca Python:
  - [`paho-mqtt`](https://pypi.org/project/paho-mqtt/)
- Acesso à Internet (para conectar ao broker público `broker.emqx.io`)

> Você pode baixar o código via **Git clone** ou pelo botão **Code → Download ZIP** no GitHub.

---

## ⚙️ Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/Igorsarcinelli/Comunica-o-Indireta-Pub-Sub-Elei-o-e-Coordena-o.git
cd Comunica-o-Indireta-Pub-Sub-Elei-o-e-Coordena-o
````

### 2. Instalar dependências

```bash
python -m pip install --upgrade pip
pip install paho-mqtt
```

---

## ▶️ Como executar o sistema

Cada instância de `Minerador.py` representa **um nó** do sistema distribuído.
Para simular vários nós, é preciso abrir vários terminais e executar o mesmo comando em cada um.

### 1. Parâmetro `N` (número de participantes)

O número de nós participantes é passado como argumento na linha de comando:

```bash
python Minerador.py N
```

* Se **N** não for informado, o valor padrão é `3`.

### 2. Exemplo: execução com 4 nós

1. Abra **4 terminais** na pasta do projeto.

2. Em **cada terminal**, execute:

   ```bash
   python Minerador.py 4
   ```

3. Observe o comportamento nos logs:

* **Fase INIT**
  Cada nó gera um `ClientID` e anuncia sua presença no tópico `sd/init`, exibindo mensagens como:
  `Aguardando pares... Sincronizados: X/4`.

* **Fase ELECTION (eleição de líder)**
  Após descobrir todos os participantes, os nós entram no estado de eleição:

  * Cada nó gera um `VoteID` aleatório e o publica em `sd/voting`;
  * Todos coletam os votos e elegem o líder com base no maior `VoteID`, com desempate pelo maior `ClientID`;
  * Um nó registra: `Resultado: Líder XXXX. Papel assumido: CONTROLADOR.`;
  * Os demais registram: `Papel assumido: MINERADOR. Aguardando desafios do Controlador...`.

* **Fase RUNNING (execução/mineração)**

  * O **CONTROLADOR**:

    * gera transações (`T1`, `T2`, ...) com um valor de dificuldade (`Challenge`);
    * publica desafios em `sd/challenge`;
    * recebe soluções em `sd/solution`, valida o hash e publica o resultado em `sd/result`.
  * Os **MINERADORES**:

    * recebem os desafios;
    * iniciam uma thread de mineração (`MineradorThread`);
    * testam diferentes valores de `nonce` na string `TransactionID:Nonce` até encontrar um hash SHA-1 com o número de zeros exigido pela dificuldade;
    * quando encontram uma solução válida, publicam no tópico `sd/solution`.

---

## 🧪 Relatório técnico

### 1. Metodologia de implementação

A solução foi implementada em Python com apoio da biblioteca `paho-mqtt`, utilizando o broker público `broker.emqx.io` (porta 1883). A lógica de cada nó está encapsulada na classe `Participante`, responsável por:

* gerenciar a conexão MQTT (publicações e assinaturas);
* manter o estado do nó (`INIT`, `ELECTION`, `RUNNING`);
* executar a fase de descoberta de participantes, eleição de líder e operação (controle/mineração).

Principais componentes:

* **Comunicação via MQTT**

  * Tópico `sd/init`: anúncios de presença e descoberta de participantes (fase INIT);
  * Tópico `sd/voting`: envio e coleta de votos (`VoteID`) para eleição de líder;
  * Tópico `sd/challenge`: publicação de desafios (`TransactionID`, `Challenge`) pelo líder;
  * Tópico `sd/solution`: envio de soluções (`Solution = "TransactionID:Nonce"`) pelos mineradores;
  * Tópico `sd/result`: publicação do resultado da transação (`Winner`, `Result`) pelo líder.

* **Prova de trabalho (Proof of Work)**
  A função `check_solution(challenge, solution_string)` calcula o hash SHA-1 de `"TransactionID:Nonce"` e verifica se o hash começa com uma quantidade de zeros igual à dificuldade (`challenge`).
  A classe `MineradorThread` é responsável por:

  * iterar valores de `nonce`;
  * chamar `check_solution`;
  * parar quando encontra uma solução válida e publicar em `sd/solution`.

* **Eleição de líder**

  * Cada nó gera um `VoteID` aleatório;
  * Armazena os votos recebidos em `election_votes`;
  * O líder é o nó com maior `VoteID` (critério principal) e, em caso de empate, com maior `ClientID`;
  * O líder assume `is_leader = True` e o papel de CONTROLADOR; os demais tornam-se MINERADORES.

---

### 2. Metodologia de testes

Foram realizados testes práticos abrindo múltiplas instâncias do programa e observando o comportamento nos logs:

1. **Execução base com N = 4 nós**

   * Quatro terminais executando `python Minerador.py 4`.
   * Avaliação das fases:

     * INIT: verificação do alcance de “Sincronizados: 4/4”;
     * ELECTION: confirmação de que apenas um nó é eleito CONTROLADOR e os demais se tornam MINERADORES;
     * RUNNING: observação da geração de desafios, mineração e validação de soluções.

2. **Variação do número de participantes (N = 2 e N = 3)**

   * Execuções com 2 e 3 nós, ajustando o parâmetro `N`.
   * Verificado que:

     * a descoberta de participantes se adapta ao valor de N;
     * a eleição continua produzindo um único líder;
     * a mineração funciona normalmente com grupos menores.

3. **Variação da dificuldade da prova de trabalho**

   * Ajuste manual do valor de `Challenge` para testar desafios mais fáceis e mais difíceis.
   * Em dificuldades menores, as soluções foram encontradas rapidamente; em dificuldades maiores, o tempo de mineração aumentou significativamente, como esperado em mecanismos de PoW.

4. **Simulação de falhas de nós**

   * **Falha de minerador:** ao encerrar um nó minerador, o líder continuou publicando desafios e os mineradores restantes mantiveram a mineração.
   * **Falha do líder (CONTROLADOR):** ao encerrar o líder, novos desafios deixaram de ser publicados, evidenciando um **ponto único de falha** e a ausência de reeleição automática na versão atual do sistema.

---

### 3. Resultados e conclusões

Os testes demonstraram que:

* A fase de **inicialização** permite sincronizar corretamente os participantes via `sd/init`.
* O algoritmo de **eleição de líder** funciona de forma distribuída, com todos os nós concordando sobre quem é o CONTROLADOR e quem são os MINERADORES.
* A **prova de trabalho** é executada como planejado: mineradores encontram soluções válidas e o líder valida e registra o vencedor de cada transação.
* A **variação do número de nós** influencia apenas a concorrência na mineração, sem quebrar a lógica do protocolo.
* A **dificuldade** impacta diretamente o tempo de mineração, refletindo o comportamento esperado de algoritmos PoW.
* A arquitetura atual é capaz de tolerar a falha de mineradores, mas depende de um único líder, o que interrompe a geração de novos desafios em caso de falha do CONTROLADOR.

Em síntese, o projeto cumpre o objetivo de demonstrar, de forma prática, os conceitos de **comunicação indireta via Pub/Sub, eleição de líder, coordenação centralizada e prova-de-trabalho em um sistema distribuído**.

---

## 👤 Autores

* **Caio Zottele Mendes**
* **Igor Sarcinelli Santos**

Disciplina: **Programação Distribuída e Paralela – Laboratório III**
Curso: **Engenharia de Computação**
Instituição: **MULTIVIX – Vitória/ES**

```
```
