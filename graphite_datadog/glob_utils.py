# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Globbing utility module."""

from enum import Enum
import itertools
import re

# http://graphite.readthedocs.io/en/latest/render_api.html#paths-and-wildcards
_GRAPHITE_GLOB_RE = re.compile(r"^[^*?{}\[\]]+$")


def _is_graphite_glob(metric_component):
    """Return whether a metric component is a Graphite glob."""
    return _GRAPHITE_GLOB_RE.match(metric_component) is None


def _is_valid_glob(glob):
    """Check whether a glob pattern is valid.

    It does so by making sure it has no dots (path separator) inside groups,
    and that the grouping braces are not mismatched. This helps doing useless
    (or worse, wrong) work on queries.

    Args:
      glob: Graphite glob pattern.

    Returns:
      True if the glob is valid.
    """
    depth = 0
    for c in glob:
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                # Mismatched braces
                return False
        elif c == ".":
            if depth > 0:
                # Component separator in the middle of a group
                return False
    # We should have exited all groups at the end
    return depth == 0


class TokenType(Enum):
    """Represents atomic types used to tokenize Graphite globbing patterns."""

    PATH_SEPARATOR = 0
    LITERAL = 1
    WILD_CHAR = 2
    WILD_SEQUENCE = 3
    WILD_PATH = 4
    CHAR_SELECT_BEGIN = 5
    CHAR_SELECT_NEGATED_BEGIN = 6
    CHAR_SELECT_RANGE_DASH = 7
    CHAR_SELECT_END = 8
    EXPR_SELECT_BEGIN = 9
    EXPR_SELECT_SEPARATOR = 10
    EXPR_SELECT_END = 11


def tokenize(glob):
    """Convert a glob expression to a stream of tokens.

    Tokens have the form (type: TokenType, data: String).

    Args:
      glob: Graphite glob pattern.

    Returns:
      Iterator on a token stream.
    """
    SPECIAL_CHARS = ".?*[-]{,}"
    is_escaped = False
    is_char_select = False
    tmp = ""
    token = None
    i = -1
    while i + 1 < len(glob):
        i += 1
        c = glob[i]

        # Literal handling
        if is_escaped:
            tmp += c
            is_escaped = False
            continue
        elif c == "\\":
            is_escaped = True
            continue
        elif c not in SPECIAL_CHARS or (c == "-" and not is_char_select):
            if token and token != TokenType.LITERAL:
                yield token, None
                token, tmp = TokenType.LITERAL, ""
            token = TokenType.LITERAL
            tmp += c
            continue
        elif token:
            yield token, tmp
            token, tmp = None, ""

        # Special chars handling
        if c == ".":
            yield TokenType.PATH_SEPARATOR, ""
        elif c == "?":
            yield TokenType.WILD_CHAR, ""
        elif c == "*":
            # Look-ahead for wild path (globstar)
            if i + 1 < len(glob) and glob[i + 1] == "*":
                i += 1
                yield TokenType.WILD_PATH, ""
            else:
                yield TokenType.WILD_SEQUENCE, ""
        elif c == "[":
            is_char_select = True
            # Look-ahead for negated selector (not in)
            if i + 1 < len(glob) and glob[i + 1] == "!":
                i += 1
                yield TokenType.CHAR_SELECT_NEGATED_BEGIN, ""
            else:
                yield TokenType.CHAR_SELECT_BEGIN, ""
        elif c == "-":
            yield TokenType.CHAR_SELECT_RANGE_DASH, ""
        elif c == "]":
            is_char_select = False
            yield TokenType.CHAR_SELECT_END, ""
        elif c == "{":
            yield TokenType.EXPR_SELECT_BEGIN, ""
        elif c == ",":
            yield TokenType.EXPR_SELECT_SEPARATOR, ""
        elif c == "}":
            yield TokenType.EXPR_SELECT_END, ""
        else:
            raise Exception("Unexpected character '%s'" % c)

    # Do not forget trailing token, if any
    if token:
        yield token, tmp


def glob_to_regex(glob):
    """Convert a Graphite globbing pattern into a regular expression.

    This function does not check for glob validity, if you want usable regexes
    then you must check _is_valid_glob() first.

    Uses _tokenize() to obtain a token stream, then does simple substitution
    from token type and data to equivalent regular expression.

    It handles * as being anything except a dot.
    It returns a regex that only matches whole strings (i.e. ^regex$).

    Args:
      glob: Valid Graphite glob pattern.

    Returns:
      Regex corresponding to the provided glob.
    """
    ans = ""
    for token, data in tokenize(glob):
        if token == TokenType.PATH_SEPARATOR:
            ans += re.escape(".")
        elif token == TokenType.LITERAL:
            ans += re.escape(data)
        elif token == TokenType.WILD_CHAR:
            ans += "."
        elif token == TokenType.WILD_SEQUENCE:
            ans += "[^.]*"
        elif token == TokenType.WILD_PATH:
            ans += ".*"
        elif token == TokenType.CHAR_SELECT_BEGIN:
            ans += "["
        elif token == TokenType.CHAR_SELECT_NEGATED_BEGIN:
            ans += "[^"
        elif token == TokenType.CHAR_SELECT_RANGE_DASH:
            ans += "-"
        elif token == TokenType.CHAR_SELECT_END:
            ans += "]"
        elif token == TokenType.EXPR_SELECT_BEGIN:
            ans += "("
        elif token == TokenType.EXPR_SELECT_SEPARATOR:
            ans += "|"
        elif token == TokenType.EXPR_SELECT_END:
            ans += ")"
        else:
            raise Exception("Unexpected token type '%s' with data '%s'" % (token, data))
    return "^" + ans + "$"


def glob(metric_names, glob_pattern):
    """Pre-filter metric names according to a glob expression.

    Uses the dot-count and the litteral components of the glob to filter
    guaranteed non-matching values out, but may still require post-filtering.

    Args:
      metric_names: List of metric names to be filtered.
      glob_pattern: Glob pattern.

    Returns:
      List of metric names that may be matched by the provided glob.
    """
    glob_components = glob_pattern.split(".")

    globstar = None
    prefix_literals = []
    suffix_literals = []
    for (index, component) in enumerate(glob_components):
        if component == "**":
            globstar = index
        elif globstar:
            # Indexed relative to the end because globstar length is arbitrary
            suffix_literals.append((len(glob_components) - index, component))
        elif not _is_graphite_glob(component):
            prefix_literals.append((index, component))

    def maybe_matched_prefilter(metric):
        metric_components = metric.split(".")
        if globstar:
            if len(metric_components) < len(glob_components):
                return False
        elif len(metric_components) != len(glob_components):
            return False

        for (index, value) in itertools.chain(suffix_literals, prefix_literals):
            if metric_components[index] != value:
                return False

        return True

    return filter(maybe_matched_prefilter, metric_names)
