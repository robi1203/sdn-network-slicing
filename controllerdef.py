from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, udp, tcp, icmp


class UnifiedSlicingController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(UnifiedSlicingController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

        # MAC address degli host
        self.mac_h1 = "00:00:00:00:00:01"
        self.mac_h2 = "00:00:00:00:00:02"
        self.mac_h3 = "00:00:00:00:00:03"
        self.mac_h4 = "00:00:00:00:00:04"

        # Coppie autorizzate
        self.allowed_pairs = {
            (self.mac_h1, self.mac_h3),
            (self.mac_h3, self.mac_h1),
            (self.mac_h2, self.mac_h4),
            (self.mac_h4, self.mac_h2),
        }

        # Slice topologici
        self.upper_path = {1, 2, 3}
        self.lower_path = {4, 5, 6}

        # Porta per traffico video
        self.video_port = 9999

        # Slice_ports: mappa dpid → slice → porta d'uscita
        self.slice_ports = {
            1: {1: 1, 2: 2},
            4: {1: 1, 2: 2},
            2: {1: 2, 2: 1},  # esempio intermedio
            5: {1: 2, 2: 1}
        }

        self.end_swtiches = [1, 4]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=0, match=match, instructions=inst))

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath,
                                    priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        in_port = msg.match['in_port']
        dpid = datapath.id

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        if hasattr(self, "allowed_pairs") and (src, dst) not in self.allowed_pairs:
            self.logger.info("Blocked unauthorized flow: %s -> %s", src, dst)
            return

        if dpid in self.mac_to_port:
            if dst in self.mac_to_port[dpid]:
                out_port = self.mac_to_port[dpid][dst]
            elif pkt.get_protocol(udp.udp):
                udp_pkt = pkt.get_protocol(udp.udp)
                if udp_pkt.dst_port == self.video_port:
                    slice_number = 1
                else:
                    slice_number = 2
                out_port = self.slice_ports[dpid].get(slice_number, ofproto.OFPP_FLOOD)
            elif pkt.get_protocol(tcp.tcp):
                slice_number = 2
                out_port = self.slice_ports[dpid].get(slice_number, ofproto.OFPP_FLOOD)
            elif pkt.get_protocol(icmp.icmp):
                slice_number = 2
                out_port = self.slice_ports[dpid].get(slice_number, ofproto.OFPP_FLOOD)
            else:
                out_port = ofproto.OFPP_FLOOD
        elif dpid not in self.end_swtiches:
            out_port = ofproto.OFPP_FLOOD
        else:
            return

        actions = [parser.OFPActionOutput(out_port)]
        match = parser.OFPMatch(in_port=in_port, eth_src=src, eth_dst=dst)

        if msg.buffer_id != ofproto.OFP_NO_BUFFER:
            self.add_flow(datapath, 1, match, actions, msg.buffer_id)
            return
        else:
            self.add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

