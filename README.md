# SDN Network Slicing con Ryu e Mininet

Progetto per il corso di Ingegneria Informatica (Magistrale) — Università degli Studi di Napoli Federico II.

Implementazione di **Network Slicing** in un ambiente Software-Defined Networking (SDN), realizzata con **Mininet** come emulatore di rete e **Ryu** come controller OpenFlow 1.3. Il progetto esplora due forme distinte di slicing:

- **Topology Slicing** — isola il traffico tra coppie di host predefinite (H1↔H3, H2↔H4) tramite regole di forwarding basate su indirizzi MAC, garantendo percorsi dedicati e sicurezza tra le slice.
- **Service Slicing** — classifica dinamicamente il traffico in base a protocollo e porta di destinazione, assegnando priorità al traffico video (UDP/9999) rispetto al traffico standard (TCP, ICMP, UDP generico).

Include inoltre un'**estensione** con dashboard web (Flask + Chart.js) per il monitoraggio in tempo reale dei flussi rilevati dal controller.

## Struttura del repository

```
.
├── network_topo.py        # Definizione della topologia Mininet (4 host, 4 switch)
├── topology_slicing.py    # Controller Ryu — isolamento topologico via MAC
├── service_slicing.py     # Controller Ryu — prioritizzazione traffico video (UDP/9999)
├── controllerdef.py        # Controller unificato (topology + service slicing)
├── app.py                 # Dashboard Flask per il monitoraggio dei flussi
├── dashboard.html          # Template della dashboard (tabella + grafico Chart.js)
├── flow_stats.csv          # Log dei flussi registrati dal controller
└── NETWORK_SLICING.pdf     # Relazione completa del progetto
```

## Topologia

Quattro host (H1–H4) collegati a quattro switch OpenFlow (S1–S4):

- **Percorso superiore** (S1–S2–S4, 10 Mbps): dedicato al traffico video prioritario.
- **Percorso inferiore** (S1–S3–S4, 1 Mbps): traffico standard (HTTP e altro).

## Requisiti

- Python 3
- [Mininet](http://mininet.org/)
- [Ryu](https://ryu-sdn.org/) (controller OpenFlow)
- Open vSwitch
- Flask e Pandas (per la dashboard)

```bash
pip install ryu flask pandas
```

## Esecuzione

1. Avvia il controller Ryu (in un terminale):

```bash
ryu-manager topology_slicing.py
# oppure
ryu-manager service_slicing.py
```

2. Avvia la topologia Mininet (in un altro terminale):

```bash
sudo python3 network_topo.py
```

3. All'interno della CLI di Mininet, verifica la connettività:

```bash
mininet> pingall
```

4. (Opzionale) Avvia la dashboard di monitoraggio:

```bash
python3 app.py
```

La dashboard sarà raggiungibile su `http://localhost:5000`.

## Test e verifica

- **Connettività**: `pingall` conferma che H1 comunica solo con H3 e H2 solo con H4.
- **Isolamento dei percorsi**: monitoraggio con `tcpdump` sulle interfacce intermedie (es. `s1-eth2`) per verificare che il traffico attraversi lo slice corretto.
- **Prioritizzazione del traffico**: test con `iperf` (UDP sulla porta 9999 per il traffico video, TCP/UDP generico per il traffico standard) per confrontare la banda ottenuta sui due percorsi.
- **Flow table**: ispezione delle regole installate tramite `sudo ovs-ofctl dump-flows <switch>`.

## Autrice

Roberta Granata — Corso di Laurea Magistrale in Ingegneria Informatica, Università degli Studi di Napoli Federico II.
