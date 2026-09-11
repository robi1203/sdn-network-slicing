from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3

from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types


class TopologySlicingMacToPort(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(TopologySlicingMacToPort, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

        # MAC address degli host
        self.mac_h1 = "00:00:00:00:00:01"
        self.mac_h2 = "00:00:00:00:00:02"
        self.mac_h3 = "00:00:00:00:00:03"
        self.mac_h4 = "00:00:00:00:00:04"

        # Coppie autorizzate (slice)
        self.allowed_pairs = {
            (self.mac_h1, self.mac_h3),
            (self.mac_h3, self.mac_h1),
            (self.mac_h2, self.mac_h4),
            (self.mac_h4, self.mac_h2),
        }

        # Slice: mappiamo MAC a ID switch ammessi (upper/lower path)
        self.upper_path_switches = {1, 2, 3}
        self.lower_path_switches = {4, 5, 6}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Rule di default: manda tutto al controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        mod = parser.OFPFlowMod(datapath=datapath,
                                priority=0,
                                match=match,
                                instructions=inst)
        datapath.send_msg(mod)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath,
                                    buffer_id=buffer_id,
                                    priority=priority,
                                    match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath,
                                    priority=priority,
                                    match=match,
                                    instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        dst = eth.dst
        src = eth.src

        # Ignora pacchetti LLDP
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # Inizializza mac_to_port per questo switch
        self.mac_to_port.setdefault(dpid, {})

        # Aggiorna la porta del mittente
        self.mac_to_port[dpid][src] = in_port

        # Verifica che la comunicazione sia autorizzata
        if (src, dst) not in self.allowed_pairs:
            self.logger.info(" Flusso bloccato: %s → %s", src, dst)
            return

        # Verifica che il dpid sia compatibile con la slice
        if (src == self.mac_h1 and dst == self.mac_h3) or (src == self.mac_h3 and dst == self.mac_h1):
            if dpid not in self.upper_path_switches:
                self.logger.info(" H1-H3 attraversa switch fuori dalla upper slice (dpid %s)", dpid)
                return
        elif (src == self.mac_h2 and dst == self.mac_h4) or (src == self.mac_h4 and dst == self.mac_h2):
            if dpid not in self.lower_path_switches:
                self.logger.info(" H2-H4 attraversa switch fuori dalla lower slice (dpid %s)", dpid)
                return

        # Determina porta di uscita se conosciuta
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Crea flow match per rendere persistente la regola
        match = parser.OFPMatch(in_port=in_port, eth_src=src, eth_dst=dst)
        if msg.buffer_id != ofproto.OFP_NO_BUFFER:
            self.add_flow(datapath, 1, match, actions, msg.buffer_id)
            return
        else:
            self.add_flow(datapath, 1, match, actions)

        # Invia pacchetto out
        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=msg.buffer_id,
                                  in_port=in_port,
                                  actions=actions,
                                  data=data)
        datapath.send_msg(out)