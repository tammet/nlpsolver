import sys
from typing import Any

from nltk import LazySubsequence
import re
from nltk.corpus import propbank as pb, treebank, LazyCorpusLoader


from texttable import Texttable

# see: https://sites.pitt.edu/~naraehan/ling1330/lecture23_PropBank_in_NLTK.html

# If datasets have not been loaded

"""
@see: Modifiers in Propbank annotation guidelines
NOTE: Modifiers are present in Propbank release 3.4 but not in release 1.0 
that is available via nltk.download()
"""

import amrconfig

modifiers = amrconfig.pb_role_modifiers


def load_data():
    import nltk
    nltk.download("propbank")
    nltk.download("treebank")

def describe(roleset_id, do_print=False, examples=False):
    try:
        pb = init_propbank()
        rs = pb.roleset(roleset_id)
    except ValueError:
        # print(f"No PropBank role found for {roleset_id}")
        return {}

    tbl = Texttable()
    tbl.set_deco(Texttable.HEADER)
    tbl.set_cols_align(["l", "l", "l", "l"])

    roles = {}
    for role in rs.findall('roles/role'):
        f = role.attrib.get('f', "")

        rolelist = []
        for cls in role.findall("vnrole"):
            theta = cls.attrib["vntheta"]
            if theta not in rolelist:
                rolelist.append(theta)
        thetas = "|".join(rolelist)

        # print(f"ARG{role.attrib['n']}: {role.attrib['descr']} {f} {thetas}")
        key = ":ARG" + str(role.attrib['n'])
        descr = role.attrib.get("decr", "")

        mod = role.attrib.get("f", "")
        if mod:
            mod = modifiers.get(mod.upper(), mod)

        row = [key, thetas, descr, mod]
        # roles.update({key: thetas.capitalize()})
        roles.update({key: mod})
        tbl.add_row(row)

    if do_print:
        print(f"Roleset: {rs.attrib['id']} ({rs.attrib['name']}) [{inflect(roleset_id)}]")
        print(tbl.draw())

    if examples:
        print("\n=== Usage Examples ===\n")
        k = 1
        tbl = Texttable()
        tbl.set_deco(Texttable.HEADER)
        for ex in rs.findall("example"):
            text = ex.find("text").text
            text = text.replace("\n", "")
            text = " ".join(text.split())
            text = text.replace("*trace*", "")
            text = text.strip()
            tbl.add_row([ex.attrib["name"], str(text)])
        print(tbl.draw())

    #print(roles)
    return roles
    # return [[role[0], role[1]] for role in roles]





def sample():
    for item in ["abstain.01", "like.01", "stab.01", "color.01"]:
        describe(item, True, True)


def inflect(roleset_id):
    instances = propbank.instances()
    k = 0
    for inst in instances:
        if inst.roleset == roleset_id:
            break
    return inst.inflection


def explore():
    """
    Get a list of unique inflections for the whole corpus.
    """

    instances = propbank.instances()

    k = 0

    known_inflections = []

    while k < len(instances):

        # PropBankInstance
        inst = instances[k]
        # print(inst.fileid, inst.sentnum, inst.wordnum, inst.tagger, inst.inflection, inst.roleset, inst.arguments, inst.predicate)

        # PropbankInflection
        inf = str(inst.inflection)
        if inf not in known_inflections:
            known_inflections.append(inf)

            if inf[0] == "g" or True:
                print(inst.inflection, "\t", inst.roleset)


            # print(f"Roleset: {inst.roleset}, Inflection: {inst.inflection}")

        k += 1
    print(k, "Inflections:", len(known_inflections))


def init_propbank():
    """
    Overwrite reader for 'nltk.corpus.reader.propbank'
    :return:
    """

    parse_fileid_xform=lambda filename: re.sub(r"^wsj/\d\d/", "", filename)

    from nltk.corpus.reader.propbank import PropbankCorpusReader
    propbank = PropbankCorpusReader = LazyCorpusLoader(
        "propbank-3.1",
        PropbankCorpusReader,
        "prop.txt",
        framefiles=r"frames/.*\.xml",
        verbsfile="verbs.txt",
        parse_fileid_xform=parse_fileid_xform,
        parse_corpus=treebank,
    )


    """
    :param parse_corpus: The corpus containing the parse trees
        corresponding to this corpus.  These parse trees are
        necessary to resolve the tree pointers used by propbank.
    """

    return propbank



if __name__ == "__main__":

    propbank = init_propbank()

    inp = False

    if len(sys.argv) > 1:
        inp = sys.argv[1]

    if inp:
        roles = describe(inp, True, True)
        print(roles)

    else:
        roles = describe("good.02", True, True)
        # print("Done")
        # explore()
        # sample()
