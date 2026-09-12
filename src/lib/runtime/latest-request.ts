/** Request tickets cannot publish after another request, navigation or destruction. */
export function latestRequest() {
  let epoch = 0;
  return {
    begin: () => ++epoch,
    invalidate: () => { epoch += 1; },
    current: (ticket: number) => ticket === epoch,
  };
}
