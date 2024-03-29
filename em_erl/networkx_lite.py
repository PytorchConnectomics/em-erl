import numpy as np
import scipy.sparse as sp
from em_util.io import read_pkl, write_pkl

# implement a light-weight networkx graph like class with npz backend
# assumes fixed number of nodes and edges
# skeletons.nodes()
# skeletons.nodes(data=True)
# skeletons.nodes[n][attr]
# skeletons.edges()
# skeletons.edges[e][attr]
# skeletons.edges(data=True)
# return u, v, data, where data is a dict of edge attributes which can be SET


class NetworkXGraphLite:
    # The NetworkXGraphLite class is a lightweight version of the NetworkXGraph class.
    def __init__(
        self,
        node_attributes=["skeleton_id", "z", "y", "x"],
        edge_attribute="length",
        node_dtype=np.uint32,
        edge_dtype=np.float32,
    ):
        self.node_attributes = sorted(node_attributes)
        self.node_dtype = node_dtype
        # since edges will be saved as 2D dok matrix, can only take single attribute
        assert isinstance(edge_attribute, str)
        self.edge_attribute = edge_attribute
        self.edge_dtype = edge_dtype

        self._nodes = None  # will be saved as [N, #node_attributes] npz
        self._edges = None  # will be saved as dok npz

        self.nodes = None
        self.edges = None

    def init_viewers(self):
        """
        The function initializes viewers for nodes and edges.
        """
        assert self._nodes is not None
        self.nodes = NodeViewerLite(self._nodes, self.node_attributes)
        assert self._edges is not None
        self.edges = EdgeViewerLite(self._edges, self.edge_attribute)

    def get_nodes(self):
        return self._nodes

    def set_nodes(self, nodes):
        self._nodes = nodes

    def set_edges(self, edges):
        self._edges = edges

    def networkx_to_lite(self, nx_graph):
        """
        The function loads a graph into the object, ensuring that the graph nodes have the same
        attributes and storing the node and edge data in appropriate data structures.

        :param graph: The `graph` parameter is an object that represents a graph. It contains
        information about the nodes and edges of the graph
        """
        assert len(nx_graph.nodes) > 0
        # assert every node has the same attributes
        assert list(nx_graph.nodes) == list(range(len(nx_graph.nodes)))

        nodes = {key: [] for key in self.node_attributes}

        minval = np.inf
        maxval = 0
        for node in nx_graph.nodes:
            node = nx_graph.nodes[node]
            for key in self.node_attributes:
                assert key in node
                nodes[key].append(node[key])
                maxval = max(maxval, node[key])
                minval = min(minval, node[key])
        assert minval >= np.iinfo(self.node_dtype).min
        assert maxval <= np.iinfo(self.node_dtype).max
        assert len({len(nodes[key]) for key in nodes}) == 1

        self._nodes = np.stack(
            [np.array(nodes[key]) for key in self.node_attributes], axis=1
        ).astype(self.node_dtype)

        edges = sp.dok_matrix(
            (len(nx_graph.nodes), len(nx_graph.nodes)), dtype=self.edge_dtype
        )
        for edge_0, edge_1, data in nx_graph.edges(data=True):
            edge = tuple(sorted([edge_0, edge_1]))
            edges[edge] = (
                data[self.edge_attribute] if self.edge_attribute in data else -1
            )

        self._edges = edges
        self.init_viewers()

    def load_npz(self, node_npz_file, edge_npz_file):
        """
        The function `load_npz` loads node and edge data from npz files and initializes viewers.

        :param node_npz_file: The parameter `node_npz_file` is the file path to the .npz file that
        contains the data for the nodes
        :param edge_npz_file: The `edge_npz_file` parameter is a file path to a NumPy compressed sparse
        matrix file (.npz) that contains the edge data
        """
        self._nodes = np.load(node_npz_file)["data"]
        self._edges = sp.load_npz(edge_npz_file).todok()
        self.init_viewers()

    def save_npz(self, node_npz_file, edge_npz_file):
        assert self._nodes is not None
        assert self._edges is not None
        np.savez_compressed(node_npz_file, data=self._nodes)
        sp.save_npz(edge_npz_file, self._edges.tocoo())


# The NodeViewerLite class is a simplified version of a node viewer.
class NodeViewerLite:
    def __init__(self, nodes, node_attributes):
        self._nodes = nodes
        self._node_attributes = node_attributes

    def __getitem__(self, key):
        node = self._nodes[key]
        return {key: node[i] for i, key in enumerate(self._node_attributes)}

    def __call__(self, data=False):
        if not data:
            return range(len(self._nodes))
        else:
            # return generator, not instantiated list
            return ((i, self[i]) for i in range(len(self._nodes)))


# The EdgeViewerLite class is a lightweight viewer for displaying edges.
class EdgeViewerLite:
    def __init__(self, edges, edge_attribute):
        self._edges = edges
        self._edge_attribute = edge_attribute

    def __getitem__(self, key):
        key = tuple(sorted(key))
        return EdgeDataViewerLite(self._edges, self._edge_attribute, key)

    def __call__(self, data=False):
        indices = self._edges.nonzero()
        if not data:
            return ((i, j) for i, j in zip(indices[0], indices[1]))
        else:
            return ((i, j, self[i, j]) for i, j in zip(indices[0], indices[1]))


# The EdgeDataViewerLite class is a lightweight viewer for edge data.
class EdgeDataViewerLite:
    def __init__(self, edges, edge_attribute, key):
        self._edges = edges
        self._edge_attribute = edge_attribute
        self._key = key

    def __getitem__(self, edge_attribute):
        assert edge_attribute == self._edge_attribute
        return self._edges[self._key]

    def __setitem__(self, edge_attribute, value):
        assert edge_attribute == self._edge_attribute
        self._edges[self._key] = value


def networkx_to_lite(networkx_graph, data_type=np.uint16):
    """
    The function converts a NetworkX graph to a NetworkXGraphLite graph.

    :param networkx_graph: The `networkx_graph` parameter is a graph object
    from the NetworkX library. It represents a graph with nodes and edges,
    where each node can have attributes and each edge can have attributes
    :return: a NetworkXGraphLite object.
    """
    networkx_lite_graph = NetworkXGraphLite(
        ["skeleton_id", "z", "y", "x"],
        "length",
        node_dtype=data_type,
        edge_dtype=data_type,
    )
    networkx_lite_graph.load_graph(networkx_graph)
    return networkx_lite_graph


def skel_to_lite(
    skeletons, skeleton_resolution=None, node_type=np.uint16, edge_type=np.float32
):
    """
    The function `skeleton_to_networkx` converts a skeleton object into a networkx graph, with an option
    to return all nodes.

    :param skeletons: The "skeletons" parameter is a list of skeleton objects. Each skeleton object
    represents a graph structure with nodes and edges. The function converts these skeleton objects into
    a networkx graph object
    :param skeleton_resolution: The `skeleton_resolution` parameter is an optional parameter that
    specifies the resolution of the skeleton. It is used to scale the node coordinates in the skeleton.
    If provided, the node coordinates will be multiplied by the skeleton resolution
    :param return_all_nodes: The `return_all_nodes` parameter is a boolean flag that determines whether
    or not to return all the nodes in the graph. If `return_all_nodes` is set to `True`, the function
    will return both the graph object and an array of all the nodes in the graph. If `return_all,
    defaults to False (optional)
    :return: The function `skeleton_to_networkx` returns a networkx graph object representing the
    skeleton. Additionally, if the `return_all_nodes` parameter is set to `True`, the function also
    returns an array of all the nodes in the skeleton.
    """

    # node in gt_graph: physical unit
    gt_graph = NetworkXGraphLite(
        ["skeleton_id", "z", "y", "x"],
        "length",
        node_dtype=node_type,
        edge_dtype=edge_type,
    )
    count = 0
    nodes = [None] * len(skeletons)
    edges = [None] * len(skeletons)

    for skeleton_id, (_, skeleton) in enumerate(skeletons.items()):
        if len(skeleton.edges) == 0:
            continue
        node_arr = skeleton.vertices.astype(node_type)
        if skeleton_resolution is not None:
            node_arr = node_arr * np.array(skeleton_resolution).astype(node_type)

        num_arr = node_arr.shape[0]
        skel_arr = skeleton_id * np.ones([num_arr, 1], node_type)
        nodes[skeleton_id] = np.hstack([skel_arr, node_arr])

        # augment the node index
        edges[skeleton_id] = skeleton.edges + count

        count += num_arr

    gt_graph.set_nodes(np.vstack(nodes))
    del nodes

    gt_edges = sp.dok_matrix((count, count), dtype=edge_type)
    edges = np.vstack(edges)
    for edge_0, edge_1 in edges:
        edge = tuple(sorted([edge_0, edge_1]))
        gt_edges[edge] = np.linalg.norm(
            gt_graph._nodes[edge_0] - gt_graph._nodes[edge_1].astype(int)
        )
    del edges
    gt_graph.set_edges(gt_edges)
    gt_graph.init_viewers()

    return gt_graph
