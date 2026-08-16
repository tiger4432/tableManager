import { edgeCurves, filterGraph, radialLayout, readGraph, readStructure, subgraphFrom } from '../src/ledger_graph/graph_core.js';
import { mergeEntityPages, normalizeEntityCatalog } from '../src/ledger_graph/entity_catalog.js';
import { readFileSync } from 'node:fs';

let assertions=0;const ok=(condition,message)=>{assertions+=1;if(!condition)throw new Error(message)};
const body={state:'ready',seed:{id:'a'},walk:{hops_requested:20},nodes:[
  {id:'a',type:'Lot',label:'MERGED',keys:{lot:'MERGED'},depth:0},
  {id:'b',type:'Lot',label:'A',keys:{lot:'A'},depth:1},
  {id:'c',type:'Lot',label:'B',keys:{lot:'B'},depth:1},
  {id:'w',type:'Wafer',label:'WF-1',keys:{wafer:'WF-1'},depth:2},
],edges:[
  {id:'ab',source:'a',target:'b',predicate:'derived_from',witnesses:1},
  {id:'ac',source:'a',target:'c',predicate:'derived_from',witnesses:2},
  {id:'bw',source:'b',target:'w',predicate:'has_wafer',witnesses:1},
]};
const model=readGraph(body);ok(model.nodes.length===4,'reads all nodes');ok(model.edges.length===3,'reads all edges');ok(model.seedId==='a','keeps server seed');
const positions=radialLayout(model);ok(positions.get('a').x===0&&positions.get('a').y===0,'seed is center');ok(positions.get('b').depth===1&&positions.get('c').depth===1,'branch siblings share ring');
const again=radialLayout(model);ok(JSON.stringify([...positions])===JSON.stringify([...again]),'layout is deterministic');
const lots=filterGraph(model,{types:new Set(['Lot'])});ok(lots.nodes.length===3,'node type filter');ok(lots.edges.length===2,'edges require visible endpoints');
const derived=filterGraph(model,{predicates:new Set(['derived_from'])});ok(derived.edges.length===2,'predicate filter');
const searched=filterGraph(model,{text:'WF-1'});ok(searched.nodes.some((n)=>n.id==='w'),'identity search');
ok(searched.seedId==='w','filtered graph reseats the layout center');
const local=subgraphFrom(model,'w',1);ok(local.nodes.length===2&&local.edges.length===1,'node starts a bounded undirected subgraph');ok(local.seedId==='w','subgraph starts at selected node');
const catalog=normalizeEntityCatalog({entity_type:'Recipe',entity_types:[{type:'Lot',label:'랏',keys:['lot']},{type:'Recipe',label:'레시피',keys:['recipe','rev']}],items:[{id:'r4',type:'Recipe',label:'RCP-A / 4',keys:{recipe:'RCP-A',rev:'4'},register_claims:2}],page:{has_more:true,next_cursor:'next'},search:{q:'RCP'}});
ok(catalog.types.length===2&&catalog.items[0].keys.rev==='4','catalog keeps every declared type and structured identity');ok(catalog.hasMore&&catalog.nextCursor==='next','catalog keeps keyset continuation');
ok(mergeEntityPages([{id:'a'},{id:'b'}],[{id:'b'},{id:'c'}]).length===3,'catalog pages merge without duplicate entities');
const curves=edgeCurves([...model.edges,{...model.edges[0],id:'ab2'}]);ok(curves.get('ab')!==curves.get('ab2'),'parallel edges separate');
const structure=readStructure({state:'ready',cost:{atoms_counted:12},graph:{nodes:[
  {id:'Wafer',type:'Wafer',label:'웨이퍼',keys:['wafer'],atoms_as_subject:10,atoms_as_object:2,registered:3},
  {id:'Lot',type:'Lot',label:'랏',keys:['lot'],atoms_as_subject:2,atoms_as_object:0,registered:1},
],edges:[
  {id:'Lot|has_wafer|entity:Wafer',source:'Lot',target:'Wafer',subject_type:'Lot',predicate:'has_wafer',predicate_label:'웨이퍼 보유',object_kind:'entity_ref',atoms:2},
  {id:'Wafer|measured|value',source:'Wafer',target:null,subject_type:'Wafer',predicate:'measured',predicate_label:'계측',object_kind:'value',object_fields:['metric','value'],atoms:10},
]}});
ok(structure.mode==='ontology','structure response declares ontology mode');ok(structure.nodes.length===3,'value claim becomes an inspectable shape node');ok(structure.edges.length===2,'structure keeps entity and value predicates');ok(structure.seedId==='Wafer','busiest entity type is the ontology center');ok(structure.nodes.find((n)=>n.schema_kind==='claim_shape')?.object_fields.length===2,'claim shape keeps required fields');
const html=readFileSync(new URL('../ledger-graph.html',import.meta.url),'utf8');ok(html.includes('data-lg-canvas'),'page owns graph canvas');ok(html.includes('data-lg-detail-body')&&html.includes('data-lg-predicate-filters'),'two inspection rails exist');
ok(html.includes('data-lg-node-list')&&html.includes('data-lg-node-search'),'right rail has a searchable node list');ok(html.includes('data-lg-mode="ontology"')&&html.includes('data-lg-mode="lineage"'),'ontology and lineage are explicit modes');
ok(html.includes('data-lg-catalog-list')&&html.includes('data-lg-entity-type'),'global entity catalog exposes type and item lists');
ok(html.includes('Nodes CSV')&&html.includes('Edges CSV')&&html.includes('Properties CSV'),'viewer exports the stable three-table contract');
const main=readFileSync(new URL('../src/ledger_graph/main.js',import.meta.url),'utf8');ok(main.includes('AbortController'),'requests are cancellable');ok(main.includes('ResizeObserver'),'canvas follows viewport');ok(!main.includes('/graph/neighbors'),'retired graph API is not revived');ok(main.includes("kind:'node'")&&main.includes('manualPositions'),'nodes are draggable and manual positions persist through filtering');ok(main.includes('/api/ledger/structure'),'ontology reuses the canonical structure route');ok(main.includes('startFromNode'),'node list starts a subgraph');
ok(main.includes('/api/ledger/subgraph'),'every registered entity and every evidence node use the unified subgraph route');
ok(main.includes('/api/ledger/subgraph/table'),'CSV exports use the same graph walk and stable table projection');
ok(!main.includes('entityQuery.value=selection.label'),'opening a graph does not erase its source catalog with a formatted label search');
ok(main.includes("node.node_kind==='action'"),'Enrich Action has a distinct graph glyph');
ok(main.includes('<h3>Enrich Action</h3>'),'action detail explains state, missing targets and next step');
ok(main.includes("enrich_actions:'true'"),'evidence walk and table exports explicitly request action projection');
const catalogSource=readFileSync(new URL('../src/ledger_graph/entity_catalog.js',import.meta.url),'utf8');ok(catalogSource.includes('AbortController')&&catalogSource.includes("params.set('after'"),'catalog search has stale cancellation and keyset paging');ok(!catalogSource.includes('/lot_catalog'),'catalog is not Lot-specific');
console.log(`ASSERTIONS ${assertions} 0`);
