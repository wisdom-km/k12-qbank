/** Switch, load, and same-key retry rules for the confirm section. */

export function startSwitch(generation) {
  return generation + 1;
}

export function cleared() {
  return {
    attempt: null,
    confirmation: null,
    payload: null,
    confirmAllowed: false,
  };
}

export function acceptLoad(requestedGeneration, currentGeneration, attempt) {
  if (requestedGeneration !== currentGeneration) {
    return { apply: false, attempt: null, confirmAllowed: false };
  }
  if (attempt == null) {
    return { apply: true, attempt: null, confirmAllowed: false };
  }
  return { apply: true, attempt, confirmAllowed: true };
}

export function retryBody(storedPayload, _editedPayload) {
  return storedPayload;
}

export function showConflictReload(errorCode) {
  return errorCode === "version_mismatch";
}
