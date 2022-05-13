from flask import Flask, jsonify, request
from core.api.grpc import client
from core.api.grpc.core_pb2 import Node, NodeType, Position, SessionState

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


@app.route('/sessions/<int:session_id>/nodes', methods=['POST'])
def nodes(session_id):
    """
    :param session_id:
    :return:
    """
    node_datas = request.get_json()['nodes'] or {}
    nodes_info = []
    for node_data in node_datas:
        node_type = node_types[node_data['node_type']]
        print(node_data)
        '''
        if node_type == "default":
            node_type = NodeType.DEFAULT
        '''
        # elif
        x = node_data['node_position']['x']
        y = node_data['node_position']['y']
        node_position = Position(x=x, y=y)
        new_node = Node(type=node_type, position=node_position)
        core_response = core.add_node(session_id, new_node)
        new_node_id = core_response.node_id
        new_node_info = {'node_id': new_node_id, 'node_type': node_type}
        nodes_info.append(new_node_info)
    response = jsonify({'new_nodes_info': nodes_info})
    response.status_code = 201  # 201 created
    return response


'''
    TODO: add ifaces
'''


@app.route('/sessions/<int:session_id>/links', methods=['POST', 'DELETE', 'PUT'])
def add_links(session_id):
    """
    :param session_id:
    :return:
    """
    links_data = request.get_json()['links'] or {}
    links_info = []
    deleted_links_info = []
    if request.method == 'POST':
        for link_data in links_data:
            node1_id = link_data['node1_id']
            node2_id = link_data['node2_id']
            core.add_link(session_id=session_id, node1_id=node1_id, node2_id=node2_id)
            new_link_info = {'node1_id': node1_id, 'node2_id': node2_id}
            links_info.append(new_link_info)
        response = jsonify({'new_links_info': links_info})
        response.status_code = 201
        return response
    elif request.method == 'DELETE':
        for link_data in links_data:
            node1_id = link_data['node1_id']
            node2_id = link_data['node2_id']
            core.delete_link(session_id=session_id, node1_id=node1_id, node2_id=node2_id)
            deleted_link_info = {'node1_id': node1_id, 'node2_id': node2_id}
            deleted_links_info.append(deleted_link_info)
        response = jsonify({'deleted_links_info':deleted_links_info})
        response.status_code = 205
        return response

