pb_role_modifiers = {
    "COM": "Comitative",
    "LOC": "Locative",
    "DIR": "Directional",
    "GOL": "Goal",
    "MNR": "Manner",
    "TMP": "Temporal",
    "EXT": "Extent",
    "REC": "Reciprocals",
    "PRD": "Secondary_Predication",
    "PRP": "Purpose",
    "CAU": "Cause",
    "DIS": "Discourse",
    "ADV": "Adverbials",
    "ADJ": "Adjectival",
    "MOD": "Modal",
    "NEG": "Negation",
    "DSP": "Direct_Speech",
    "LVB": "Light_Verb",
    "CXN": "Construction",
    "PAG": "Agent",
    "PPT": "Patient",
    "VSP": "Verb-specific"
}


# source: https://www.isi.edu/~ulf/amr/lib/amr-dict.html
# Roles: https://github.com/amrisi/amr-guidelines/blob/master/amr.md#special-frames-for-roles
amr_dict_roles = {
    'have-rel-role-91': {
        'roles': {
            ':ARG0': 'entityA',
            ':ARG1': 'entityB',
            ':ARG2': 'entityA_role',
            ':ARG3': 'entityB_role',
            ':ARG4': 'Basis'  # relationship basis (contract, case; rarely used)
        }
    },
    'have-org-role-91': {
        'roles': {
            ':ARG0': "Agent",
            ':ARG1': 'Organization',
            ':ARG2': 'Role',
            ':ARG4': 'Responsibility'
        }
    },
    "have-degree-91": { # https://www.isi.edu/~ulf/amr/ontonotes-4.0-frames/have-degree-v.html
        "roles": {
            ":ARG0": "Entity",
            ":ARG1": "Attribute",
            ":ARG2": "Degree",
            ":ARG3": "Compared-to",
            ":ARG4": "Superlative",
            ":ARG5": "Reference"
        }
    }
}


# AMR clausification: dev output
dev_debug = {
    "debug_amr": False,
    "debug_propbank": True,
    "debug_triples": False,
    "debug_get_attribute_values": False,
    "debug_print_edges": False,
    "debug_attribute_value_map": False,
    "debug_concept_values": False,
    "debug_concept_edges": False,
    "debug_attr_value_map": False,
    "debug_edge_replacements": False,
    "debug_clauses": False,
    "debug_warnings": False
}

locals().update(dev_debug)