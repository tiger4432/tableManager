// The sub-structure of a claim's `emit`, in ONE place.
//
// 🔴 WHY THIS EXISTS, AND WHY ONLY THIS. The owner's rule is 「값이 없다면 빈 폼으로 해당
// 요소의 하위 json 구조가 폼으로 뜨게」, and a form for something ABSENT cannot be derived
// from anything the system currently publishes: the authoring plan walks what the document
// holds, so an absent `emit` has no rows, and the validator names `emit` but describes its
// shape only in English prose. Claims and roles escape this because their members are named
// by the operator; `emit` does not -- its members are fixed by the grammar.
//
// So the grammar is written down once, here, for the one place that needs it.
//
// 🔴 IT IS A GUIDE, NOT A GATE, and it can drift. `setup_bundle.py` is the first author of
// this contract; this is a second statement of part of it. So it never refuses anything: it
// only offers fields, the raw JSON editor still reaches everything it does not know, and the
// validator remains the only thing that decides whether a declaration is good. If the two
// disagree, the validator is right and this file is stale.
//
// 🔴 NO CLOSED LIST IS COPIED HERE. `choice` names a key of `/authoring/schema`
// (`closed_lists()`), whose docstring is the rule: "The screen renders what this returns and
// owns no copy." Only the STRUCTURE lives here; the values stay on the server.
//
// Field kinds:
//   ref     a name of another declaration -- suggested from the plan's candidates, never forced
//   roles   a `$role` of the claim this emit belongs to -- read from the sibling roles
//   choice  one of a closed list the server publishes
//   object  a nested block, described by `of`

export const EMIT_SHAPE = [
  { key: 'predicate', kind: 'ref', label: '술어' },
  { key: 'subject', kind: 'roles', label: '주어' },
  { key: 'occurred_at', kind: 'roles', label: '시각' },
  {
    key: 'object',
    kind: 'object',
    label: '목적어',
    of: [
      { key: 'kind', kind: 'choice', list: 'object_kind', label: '종류' },
      { key: 'value', kind: 'roles', label: '값' },
    ],
  },
];
