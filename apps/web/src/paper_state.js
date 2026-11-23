/** Page state for the synthetic issue loop. One reducer, no second copy in a ref. */

export const initialPaperState = {
  session: null,
  items: [],
  item: null,
  studentId: "student-synth",
  paper: null,
  papers: [],
  attempt: null,
  decision: "adopt",
  operationKey: "key-web-1",
  confirmation: null,
  savedPayload: null,
  message: "",
  error: "",
  errorCode: "",
  issuing: false,
};

export function paperReducer(state, action) {
  if (!action || action.type !== "set" || !Object.prototype.hasOwnProperty.call(state, action.key)) {
    return state;
  }
  const current = state[action.key];
  const value = typeof action.value === "function" ? action.value(current) : action.value;
  if (Object.is(value, current)) return state;
  return { ...state, [action.key]: value };
}

export function createPaperStore(start = initialPaperState) {
  let current = {
    ...start,
    papers: (start.papers || []).map((row) => ({ ...row })),
    items: (start.items || []).map((row) => ({ ...row })),
  };
  function set(key) {
    return (value) => {
      current = paperReducer(current, { type: "set", key, value });
    };
  }
  return { get: () => current, set };
}
