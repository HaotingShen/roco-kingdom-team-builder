/**
 * Username validation with Chinese character support.
 *
 * Requirements:
 * - Allowed: Latin letters (A-Z a-z), digits (0-9), Chinese Han characters, underscore, hyphen
 * - Disallowed: spaces, emoji, symbols, punctuation (except _/-), control chars, zero-width chars
 * - Length: 2-16 graphemes (user-perceived characters)
 * - Security: Detect confusable/look-alike characters
 *
 * Clean name rules:
 * - Trim whitespace (including full-width) before validation
 * - Cannot start or end with separators (_ or -)
 * - No consecutive separators (__, --, _-, -_)
 * - Must contain at least one letter or Chinese character (not digits-only)
 */

// Allowed character pattern:
// - ASCII letters: a-zA-Z
// - Digits: 0-9
// - Underscore and hyphen: _-
// - CJK Unified Ideographs: \u4e00-\u9fff
// - CJK Extension A: \u3400-\u4dbf
const ALLOWED_CHARS_REGEX = /^[a-zA-Z0-9_\u4e00-\u9fff\u3400-\u4dbf-]+$/;

// Disallowed patterns
const SPACES_REGEX = /[\s\u00A0\u3000\u2002-\u200B]/; // Various space chars including full-width
const CONTROL_CHARS_REGEX = /[\x00-\x1f\x7f-\x9f]/; // ASCII and Latin-1 control chars
const ZERO_WIDTH_REGEX = /[\u200B-\u200F\u2028-\u202F\uFEFF\u2060-\u206F]/; // Zero-width and format chars

// Emoji detection (simplified but covers common cases)
const EMOJI_REGEX =
  /[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F700}-\u{1F77F}\u{1F780}-\u{1F7FF}\u{1F800}-\u{1F8FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{2702}-\u{27B0}\u{1F1E0}-\u{1F1FF}]/u;

// Clean name patterns
const CONSECUTIVE_SEPARATORS_REGEX = /[_-]{2,}/; // Two or more separators in a row
const HAS_LETTER_REGEX = /[a-zA-Z\u4e00-\u9fff\u3400-\u4dbf]/; // At least one letter
const SEPARATORS = "_-";

// Whitespace to trim (including full-width space)
const TRIM_CHARS = /^[\s\u00A0\u3000]+|[\s\u00A0\u3000]+$/g;

// Confusable characters (Cyrillic, Greek, full-width that look like Latin)
const CONFUSABLES: Record<string, string> = {
  // Cyrillic look-alikes for Latin
  а: "a", е: "e", о: "o", р: "p", с: "c", х: "x",
  А: "A", В: "B", Е: "E", К: "K", М: "M", Н: "H",
  О: "O", Р: "P", С: "C", Т: "T", Х: "X",
  // Greek look-alikes
  α: "a", ο: "o", ρ: "p",
  Α: "A", Β: "B", Ε: "E", Η: "H", Ι: "I", Κ: "K",
  Μ: "M", Ν: "N", Ο: "O", Ρ: "P", Τ: "T", Χ: "X", Υ: "Y",
  // Full-width Latin
  Ａ: "A", Ｂ: "B", Ｃ: "C", Ｄ: "D", Ｅ: "E", Ｆ: "F",
  Ｇ: "G", Ｈ: "H", Ｉ: "I", Ｊ: "J", Ｋ: "K", Ｌ: "L",
  Ｍ: "M", Ｎ: "N", Ｏ: "O", Ｐ: "P", Ｑ: "Q", Ｒ: "R",
  Ｓ: "S", Ｔ: "T", Ｕ: "U", Ｖ: "V", Ｗ: "W", Ｘ: "X",
  Ｙ: "Y", Ｚ: "Z",
  ａ: "a", ｂ: "b", ｃ: "c", ｄ: "d", ｅ: "e", ｆ: "f",
  ｇ: "g", ｈ: "h", ｉ: "i", ｊ: "j", ｋ: "k", ｌ: "l",
  ｍ: "m", ｎ: "n", ｏ: "o", ｐ: "p", ｑ: "q", ｒ: "r",
  ｓ: "s", ｔ: "t", ｕ: "u", ｖ: "v", ｗ: "w", ｘ: "x",
  ｙ: "y", ｚ: "z",
  // Full-width digits
  "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
  "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
};

/**
 * Count graphemes (user-perceived characters) in a string.
 * Uses Intl.Segmenter for accurate grapheme counting.
 */
function countGraphemes(str: string): number {
  // Use Intl.Segmenter if available (modern browsers)
  if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
    const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
    return [...segmenter.segment(str)].length;
  }
  // Fallback: normalize and count code points (less accurate for complex emoji)
  return [...str.normalize("NFC")].length;
}

/**
 * Trim whitespace from username, including full-width spaces.
 */
function trimUsername(username: string): string {
  return username.replace(TRIM_CHARS, "");
}

/**
 * Validate a username and return an error message if invalid.
 *
 * @param username - The username to validate
 * @param t - Translation function for localized error messages
 * @returns Error message string if invalid, null if valid
 */
export function validateUsername(
  username: string,
  t: (key: string, vars?: Record<string, unknown>) => string
): string | null {
  if (!username) {
    return t("auth.usernameEmpty");
  }

  // Trim whitespace (including full-width spaces)
  const trimmed = trimUsername(username);
  if (!trimmed) {
    return t("auth.usernameEmpty");
  }

  // Normalize for validation
  const normalized = trimmed.normalize("NFC");

  // Check for control characters
  if (CONTROL_CHARS_REGEX.test(normalized)) {
    return t("auth.usernameInvalidChars");
  }

  // Check for zero-width characters
  if (ZERO_WIDTH_REGEX.test(normalized)) {
    return t("auth.usernameInvisibleChars");
  }

  // Check for spaces (after trimming, internal spaces)
  if (SPACES_REGEX.test(normalized)) {
    return t("auth.usernameNoSpaces");
  }

  // Check for emoji
  if (EMOJI_REGEX.test(normalized)) {
    return t("auth.usernameNoEmoji");
  }

  // Check allowed character set
  if (!ALLOWED_CHARS_REGEX.test(normalized)) {
    return t("auth.usernameInvalidChars");
  }

  // Check leading/trailing separators
  if (SEPARATORS.includes(normalized.charAt(0))) {
    return t("auth.usernameNoLeadingSeparator");
  }
  if (SEPARATORS.includes(normalized.charAt(normalized.length - 1))) {
    return t("auth.usernameNoTrailingSeparator");
  }

  // Check consecutive separators
  if (CONSECUTIVE_SEPARATORS_REGEX.test(normalized)) {
    return t("auth.usernameNoConsecutiveSeparators");
  }

  // Check for digits-only (must have at least one letter)
  if (!HAS_LETTER_REGEX.test(normalized)) {
    return t("auth.usernameNeedsLetter");
  }

  // Check grapheme length
  const length = countGraphemes(normalized);
  if (length < 2) {
    return t("auth.usernameTooShort");
  }
  if (length > 16) {
    return t("auth.usernameTooLong");
  }

  // Check for confusable characters
  for (const char of normalized) {
    if (char in CONFUSABLES) {
      return t("auth.usernameConfusable", { char });
    }
  }

  return null;
}
