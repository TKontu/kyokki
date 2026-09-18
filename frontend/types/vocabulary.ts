/**
 * Vocabulary values the API may grow without a frontend release (H04).
 */

/**
 * `T`, plus any other string the API might send.
 *
 * The iPad runs unattended, so a value this build does not know must still render: dropping it
 * blanks a card and substituting a default tells the cook something untrue. Screens therefore
 * show the raw string, and this type is what lets them.
 *
 * The intersection with an empty object is the usual trick that keeps editor completion for the
 * known members of `T` instead of collapsing the whole union to `string`.
 */
export type Vocabulary<T extends string> = T | (string & Record<never, never>)
