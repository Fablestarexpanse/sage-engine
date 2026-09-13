import ELK from "elkjs/lib/elk.bundled.js";

/**
 * @param {import('@xyflow/react').Node[]} nodes
 * @param {import('@xyflow/react').Edge[]} edges
 * @param {string} algorithm elk algorithm id
 */
export async function layoutGraph(nodes, edges, algorithm = "layered") {
  if (!nodes.length) return nodes;
  const elk = new ELK();
  const graph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": algorithm,
      "elk.spacing.nodeNode": "80",
      "elk.layered.spacing.nodeNodeBetweenLayers": "100",
    },
    children: nodes.map((n) => ({
      id: n.id,
      width: 190,
      height: 88,
    })),
    edges: edges.map((e) => ({
      id: e.id,
      sources: [e.source],
      targets: [e.target],
    })),
  };
  const result = await elk.layout(graph);
  const posById = new Map((result.children || []).map((c) => [c.id, { x: c.x ?? 0, y: c.y ?? 0 }]));
  return nodes.map((node) => {
    const p = posById.get(node.id);
    return p ? { ...node, position: { x: p.x, y: p.y } } : node;
  });
}
