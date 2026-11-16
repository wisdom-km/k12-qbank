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

export function acceptResponse(requestedGeneration, currentGeneration, body) {
  if (requestedGeneration !== currentGeneration) {
    return { apply: false, body: null };
  }
  return { apply: true, body };
}

export function attemptBlock(errorCode) {
  if (errorCode !== "attempt_not_current") {
    return null;
  }
  return {
    confirmAllowed: false,
    notice: "当前无法确认。这一版复核还没有作答。",
    nextStep: "重新打开这张卷",
  };
}

export function retryBody(storedPayload, _editedPayload) {
  return storedPayload;
}

export function showConflictReload(errorCode) {
  return errorCode === "version_mismatch";
}
