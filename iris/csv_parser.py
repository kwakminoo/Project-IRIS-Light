"""Simple CSV line parser.
Handles fields optionally quoted with double quotes. Commas inside quoted
fields are treated as part of the field. Double quotes inside a quoted
field are escaped by a pair of double quotes ("""). No support for
newlines, different delimiters, or complex CSV features.
"""

from typing import List

def parse_csv_line(line: str) -> List[str]:
    """Parse a single CSV line.

    Args:
        line: The CSV line to parse.
    Returns:
        A list of field strings.
    """
    fields = []
    field_chars = []
    in_quotes = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            if in_quotes:
                # Check for escaped double quote
                if i + 1 < len(line) and line[i + 1] == '"':
                    field_chars.append('"')
                    i += 1  # skip the escape char
                else:
                    in_quotes = False
            else:
                in_quotes = True
        elif ch == ',' and not in_quotes:
            fields.append(''.join(field_chars))
            field_chars = []
        else:
            field_chars.append(ch)
        i += 1
    # Append last field
    fields.append(''.join(field_chars))
    return fields
