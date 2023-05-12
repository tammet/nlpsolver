import re


def all_strings(e):
    for it in e:
        if not is_string(it):
            # print("AS", e, False)
            return False
    # print("AS", e, True)
    return True


def is_string(e):
    return isinstance(e, str)


def is_edge(e):
    return is_list(e) and is_edge_declaration(e)


def is_edge_declaration(e):
    return is_string(e) and e.startswith(":")


def is_string(e):
    return isinstance(e, str)


def is_op(e):
    return bool(re.match(":op[0-9]+", e))


def is_list(e):
    return isinstance(e, list)


def is_assignment(e):
    # [':ARG1', ['l2', 'light']]
    if not is_list(e):
        return False
    if not len(e) == 2:
        return False
    if not is_string(e[0]):
        return False
    if not is_list(e[1]):
        return False

    # print("is_assignment", len(e), e)
    return True


def is_tuple(e):
    return isinstance(e, tuple)


def is_verb(e):
    return bool(re.match("([a-z])+-[0-9]{2}", e))


def is_atom(e):
    if not is_list(e):
        return False
    if not len(e) == 2:
        return False
    if not all_strings(e):
        return False
    return True


def is_variable_assignment(e):
    if not is_atom(e):
        return False
    if is_op(e):
        return False
    return True


def dict_find_key(input_dict, value):
    for key, val in input_dict.items():
        if val == value: return key
    return None
