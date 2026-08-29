% The basic birds example in GKTPTP: standard TPTP CNF, with gk's metadata
% (confidence, blockers) in the optional useful_info field. This is a 1:1
% translation of bird_penguin.js and bird_penguin.gkp: gk converts all three
% to the same JSON-LD-LOGIC before proving. See Doc/input_languages.md.
%
% The source field is left empty here (",,"), which gk's reader allows; a
% file that must also parse under strict TPTP tools would write the filler
% source "unknown" instead.

cnf(b_is_a_bird, axiom,
    ( bird(b) ) ).

cnf(p_is_a_penguin, axiom,
    ( penguin(p) ),,
    [confidence(0.8)] ).

cnf(penguins_are_birds, axiom,
    ( ~ penguin(X) | bird(X) ) ).

cnf(penguins_do_not_fly, axiom,
    ( ~ penguin(X) | ~ flies(X) ),,
    [confidence(0.9)] ).

cnf(birds_fly, axiom,
    ( ~ bird(X) | flies(X) ),,
    [unless(~ flies(X), 2)] ).

cnf(who_does_not_fly, conjecture,
    ( ~ flies(X) ) ).
