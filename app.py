from flask import Flask, jsonify, request
from core.api.grpc import client
from core.api.grpc.core_pb2 import Node, NodeType, Position, SessionState, Interface, LinkOptions, Geo
import math
from flask_cors import cross_origin
import time
EARTH_RADIUS = 6378.137

app = Flask(__name__)
core = client.CoreGrpcClient()
core.connect()

node_types = {'default': NodeType.DEFAULT,
              'physical': NodeType.PHYSICAL,
              'switch': NodeType.SWITCH,
              'hub': NodeType.HUB,
              'wireless_lan': NodeType.WIRELESS_LAN,
              'rj45': NodeType.RJ45,
              'tunnel': NodeType.TUNNEL,
              'emane': NodeType.EMANE,
              'peer_to_peer': NodeType.PEER_TO_PEER,
              'control_net': NodeType.CONTROL_NET,
              'docker': NodeType.DOCKER,
              'lxc': NodeType.LXC
              }

# {node_id:[ip...]}
ifaces = {}
# {(node_id,ip):iface}
iface_objects = {}
all_links = []


@app.route('/sessions', methods=['POST'])
def create_session():
    response = core.create_session()
    session_id = response.session_id
    session_dict = {'session_id': session_id}
    response = jsonify(session_dict)
    response.status_code = 201
    return response


'''
TODO: combine with /nodes , delete a list of nodes
'''


@app.route('/sessions/<int:session_id>/nodes/<int:node_id>', methods=['DELETE'])
def delete_node(session_id, node_id):
    """
    :param session_id:
    :param node_id:
    :return:
    """

    '''
    should check if the node exists?
    '''
    if request.method == 'DELETE':
        core_response = core.delete_node(session_id=session_id, node_id=node_id)
        response = jsonify({'deleted node': node_id})
        response.status_code = 205
        return response


@app.route('/sessions/<int:session_id>/nodes', methods=['POST', 'OPTIONS'])
@cross_origin()
def nodes(session_id):
    """
    :param session_id:
    :return:
    """
    if request.method == 'OPTIONS':
        response = {"status": "pass options"}
        response = jsonify(response)
        response.status_code = 202
        headers = {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST'
        }
        response.headers = headers
        return response
    #print(request.get_json())
    node_datas = request.get_json()['jsonnodes']['nodes'] or {}
    # node_datas = request.get_json()['jsondata']['nodes']['data'] or {}
    #print(node_datas)
    nodes_info = []
    for node_data in node_datas:
        # node_type = node_types[node_data['node_type']]
        node_id = node_data['id']
        node_type = node_data['node_type']
        if node_type == 'sat' or node_type == 'ue' or node_type == 'gs':
            node_type = NodeType.DEFAULT
        '''
        if node_type == "default":
            node_type = NodeType.DEFAULT
        '''
        # lat
        x = float(node_data['node_position']['x'])
        # lon
        y = float(node_data['node_position']['y'])
        # alt
        z = float(node_data['node_position']['z'])
        # node_position = Position(x=x, y=y)
        # new_node = Node(type=node_type, position=node_position)
        geo = Geo(lat=x, lon=y, alt=z)
        new_node = Node(id=node_id, type=node_type, geo=geo)
        core_response = core.add_node(session_id, new_node)
        new_node_id = core_response.node_id
        new_node_info = {'node_id': new_node_id, 'node_type': node_type}
        nodes_info.append(new_node_info)
    response = jsonify({'new_nodes_info': nodes_info})
    response.status_code = 200
    return response


def rad(d):
    return d * math.pi / 180.0


def calculate_delay(session_id, node1_id, node2_id):
    """

    :param session_id:
    :param node1_id:
    :param node2_id:
    :return: the delay of a wired link between two nodes(100 ms per 3000km)
    """
    node1 = core.get_node(session_id=session_id, node_id=node1_id).node
    node2 = core.get_node(session_id=session_id, node_id=node2_id).node
    geo1 = node1.geo
    geo2 = node2.geo
    rad_lat1 = rad(geo1.lat)
    rad_lat2 = rad(geo2.lat)
    a = rad_lat1 - rad_lat2
    b = rad(geo1.lon) - rad(geo2.lon)
    s = 2 * math.asin(math.sqrt(
        math.pow(math.sin(a / 2), 2) + math.cos(rad_lat1) * math.cos(rad_lat2) * math.pow(math.sin(b / 2), 2)))
    s = s * EARTH_RADIUS
    s = math.sqrt(s * s + (geo1.alt - geo2.alt) * (geo1.alt - geo2.alt))
    # 3.333 us per km
    return int(s*3)


@app.route('/sessions/<int:session_id>/nodes', methods=['PUT'])
def edit_nodes(session_id):
    """
    :param session_id:
    :return:
    """
    node_datas = request.get_json()['nodes'] or {}
    nodes_info = {"nodes_info": []}
    links_delay = []
    for node_data in node_datas:
        node_id = node_data['node_id']
        lat = float(node_data['lat'])
        lon = float(node_data['lon'])
        alt = float(node_data['alt'])
        geo = Geo(lat=lat, lon=lon, alt=alt)
        core.edit_node(session_id=session_id, node_id=node_id, geo=geo)
        node_info = {"node_id": node_id, "new_node_geo": [lat, lon, alt]}
        nodes_info["nodes_info"].append(node_info)
        for link in all_links:
            if link[0] == node_id or link[1] == node_id:
                delay = calculate_delay(session_id, link[0], link[1])
                iface1_id = link[2]
                iface2_id = link[3]
                print(link)
                print(delay)
                option = LinkOptions(delay=delay)
                core.edit_link(session_id=session_id,
                               node1_id=link[0],
                               node2_id=link[1],
                               iface1_id=iface1_id,
                               iface2_id=iface2_id,
                               options=option)
                links_delay.append({str(link[0]) + " to " + str(link[1]): delay})
    nodes_info["new_link_delays(us)"] = links_delay
    response = jsonify(nodes_info)
    response.status_code = 200
    return response


@app.route('/sessions/<int:session_id>/links', methods=['POST', 'DELETE', 'OPTIONS'])
@cross_origin()
def links(session_id):
    """
    :param session_id:
    :return:
    """
    if request.method == 'OPTIONS':
        response = {"status": "pass options"}
        response = jsonify(response)
        response.status_code = 202
        headers = {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST'
        }
        response.headers = headers
        return response
    links_data = request.get_json()['jsonlinks']['links'] or {}
    print(links_data)
    links_info = []
    deleted_links_info = []
    if request.method == 'POST':
        # wait for the lst POST to complete
        time.sleep(3)
        for link_data in links_data:
            node1_id = link_data['node1_id']
            node2_id = link_data['node2_id']
            # iface1_id = link_data['iface1']
            # iface2_id = link_data['iface2']
            iface1_address = link_data['iface1_address']
            iface2_address = link_data['iface2_address']
            if node1_id not in ifaces.keys():
                ifaces[node1_id] = []
            if node2_id not in ifaces.keys():
                ifaces[node2_id] = []
            # check if the iface already exsits
            if iface1_address not in ifaces[node1_id]:
                iface1 = Interface(id=len(ifaces[node1_id]), node_id=node1_id, ip4=iface1_address.encode('utf-8'))
                ifaces[node1_id].append(iface2_address)
                iface_objects[(node1_id, iface1_address)] = iface1
            if iface2_address not in ifaces[node2_id]:
                iface2 = Interface(id=len(ifaces[node2_id]), node_id=node2_id, ip4=iface2_address.encode('utf-8'))
                ifaces[node2_id].append(iface2_address)
                iface_objects[(node2_id, iface2_address)] = iface2
            '''
            if (node1_id, iface1_address) not in ifaces:
                iface1 = Interface(node_id=node1_id, ip4=iface1_address.encode('utf-8'))
                ifaces[(node1_id, iface1_address)] = iface1
            if (node2_id, iface2_address) not in ifaces:
                iface2 = Interface(node_id=node2_id, ip4=iface2_address.encode('utf-8'))
                ifaces[(node2_id, iface2_address)] = iface2
            '''

            #print(ifaces)
            iface1 = iface_objects[(node1_id, iface1_address)]
            iface2 = iface_objects[(node2_id, iface2_address)]
            #print((iface1.id, iface2.id))
            core.add_link(session_id=session_id, node1_id=node1_id,
                          node2_id=node2_id, iface1=iface1, iface2=iface2)
            new_link_info = {'node1_id': node1_id, 'node2_id': node2_id}
            all_links.append((node1_id, node2_id, iface1.id, iface2.id))
            links_info.append(new_link_info)
        response = jsonify({'new_links_info': links_info, 'all_links': all_links})
        response.status_code = 200
        print(ifaces)
        print(response)
        return response
    elif request.method == 'DELETE':
        for link_data in links_data:
            node1_id = link_data['node1_id']
            node2_id = link_data['node2_id']
            iface1 = link_data['iface1']
            iface2 = link_data['iface2']
            all_links.remove((node1_id, node2_id))
            core.delete_link(session_id=session_id, node1_id=node1_id,
                             node2_id=node2_id, iface1_id=iface1, iface2_id=iface2)
            deleted_link_info = {'node1_id': node1_id, 'node2_id': node2_id}
            deleted_links_info.append(deleted_link_info)
        response = jsonify({'deleted_links_info': deleted_links_info})
        response.status_code = 205
        return response


@app.route('/sessions/<int:session_id>/links', methods=['PUT'])
def edit_links(session_id):
    links_data = request.get_json()['links'] or {}
    edit_links_info = []
    for link_data in links_data:
        node1_id = link_data['node1_id']
        node2_id = link_data['node2_id']
        iface1_address = link_data['iface1']
        iface2_address = link_data['iface2']
        iface1_id = iface_objects[(node1_id, iface1_address)].id
        iface2_id = iface_objects[(node2_id, iface2_address)].id
        delay = link_data['delay'] if 'delay' in link_data else 0
        loss = link_data['loss'] if 'loss' in link_data else float(0)
        bandwidth = link_data['bandwidth'] if 'bandwidth' in link_data else float(0)

        link_option = LinkOptions(delay=delay, loss=loss, bandwidth=bandwidth)
        core.edit_link(session_id=session_id, node1_id=node1_id, node2_id=node2_id,
                       iface1_id=iface1_id, iface2_id=iface2_id, options=link_option)
        edit_links_info.append({"link": str(node1_id)+" to "+str(node2_id),
                                "new_delay": delay,
                                "new_loss": loss,
                                "new_bandwidth": bandwidth})
    response = jsonify(edit_links_info)
    response.status_code = 200
    print(response)
    return response


'''
@app.route('/sessions/<int:session_id>/ifaces', methods=['POST'])
def create_ifaces(session_id):
    iface_datas = request.get_json()['ifaces_to_create'] or {}
    ifaces_info = []
    for iface_data in iface_datas:
        ip4_prefix = iface_data['ip4']
        ip6_prefix = iface_data['ip6']
        iface_helper = client.InterfaceHelper(ip4_prefix=ip4_prefix,ip6_prefix=ip6_prefix)
        for iface in iface_data['ifaces']:
            node_id = iface['node_id']
            iface_id = iface['iface_id']
            iface = iface_helper.create_iface(node_id=node_id, iface_id=iface_id)
            iface_info = {"node_id": node_id, "iface_id": iface.id, "ipv4": iface.ip4,
                          "ip4_mask": iface.ip4_mask, "ip6": iface.ip6, "ip6_mask": iface.ip6_mask}
            ifaces_info.append(iface_info)
    return jsonify(ifaces_info)
'''
