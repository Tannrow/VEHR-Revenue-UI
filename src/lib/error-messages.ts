export const FETCH_FAILED_MESSAGE = "fetch failed";

export function isFetchFailedMessage(message: string): boolean {
  return message.trim().toLowerCase() === FETCH_FAILED_MESSAGE;
}
