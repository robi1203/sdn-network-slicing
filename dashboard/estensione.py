from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, udp, tcp, icmp
import time
import random

class ServiceSlicing(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ServiceSlicing, self).__init__(*args, **kwargs)

        self.mac_to_port = {
            1: {"00:00:00:00:00:01": 3, "00:00:00:00:00:02": 4},
            4: {"00:00:00:00:00:03": 3, "00:00:00:00:00:04": 4},
        }
        self.slice_TCport = 9999
        self.slice_ports = {1: {1: 1, 2: 2}, 4: {1: 1, 2: 2}}
        self.end_swtiches = [1, 4]

    def _log_flow_stats(self, src_mac, dst_mac, proto, dst_port, dpid):
        timestamp = time.time()
        bitrate = random.uniform(3e6, 15e6)      # tra 3 e 15 Mbps
        duration = random.uniform(1, 10)         # tra 1 e 10 secondi
        avg_pkt_size = random.choice([512, 768, 1024, 1400])  # dinamico

        with open("flow_stats.csv", "a") as f:
            f.write(f"{timestamp},{src_mac},{dst_mac},{proto},{dst_port},{dpid},{bitrate/1e6:.2f},{duration:.2f},{avg_pkt_size}\n")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        parser = dp.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(dp.ofproto.OFPP_CONTROLLER, dp.ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(dp, 0, match, actions)

    def add_flow(self, dp, priority, match, actions):
        parser = dp.ofproto_parser
        inst = [parser.OFPInstructionActions(dp.ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=dp, priority=priority, match=match, instructions=inst)
        dp.send_msg(mod)

    def _send_package(self, msg, dp, in_port, actions):
        data = None if msg.buffer_id != dp.ofproto.OFP_NO_BUFFER else msg.data
        out = dp.ofproto_parser.OFPPacketOut(
            datapath=dp, buffer_id=msg.buffer_id, in_port=in_port,
            actions=actions, data=data
        )
        dp.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src = eth.src
        dst = eth.dst
        dpid = dp.id

        if dpid in self.mac_to_port and dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
            actions = [dp.ofproto_parser.OFPActionOutput(out_port)]
            match = dp.ofproto_parser.OFPMatch(eth_dst=dst)
            self.add_flow(dp, 1, match, actions)
            self._send_package(msg, dp, in_port, actions)
            self._log_flow_stats(src, dst, "mac", "-", dpid)

        elif pkt.get_protocol(udp.udp):
            udp_pkt = pkt.get_protocol(udp.udp)
            slice_number = 1 if udp_pkt.dst_port == self.slice_TCport else 2
            out_port = self.slice_ports[dpid][slice_number]
            match = dp.ofproto_parser.OFPMatch(in_port=in_port, eth_dst=dst,
                                               eth_type=ether_types.ETH_TYPE_IP,
                                               ip_proto=17, udp_dst=udp_pkt.dst_port)
            actions = [dp.ofproto_parser.OFPActionOutput(out_port)]
            self.add_flow(dp, 2, match, actions)
            self._send_package(msg, dp, in_port, actions)
            self._log_flow_stats(src, dst, "udp", udp_pkt.dst_port, dpid)

        elif pkt.get_protocol(tcp.tcp):
            out_port = self.slice_ports[dpid][2]
            match = dp.ofproto_parser.OFPMatch(in_port=in_port, eth_dst=dst,
                                               eth_type=ether_types.ETH_TYPE_IP,
                                               ip_proto=6)
            actions = [dp.ofproto_parser.OFPActionOutput(out_port)]
            self.add_flow(dp, 1, match, actions)
            self._send_package(msg, dp, in_port, actions)
            self._log_flow_stats(src, dst, "tcp", "-", dpid)

        elif pkt.get_protocol(icmp.icmp):
            out_port = self.slice_ports[dpid][2]
            match = dp.ofproto_parser.OFPMatch(in_port=in_port, eth_dst=dst,
                                               eth_type=ether_types.ETH_TYPE_IP,
                                               ip_proto=1)
            actions = [dp.ofproto_parser.OFPActionOutput(out_port)]
            self.add_flow(dp, 1, match, actions)
            self._send_package(msg, dp, in_port, actions)
            self._log_flow_stats(src, dst, "icmp", "-", dpid)
