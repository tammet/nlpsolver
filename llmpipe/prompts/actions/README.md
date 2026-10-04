# Action prompts

These files are the prompts of the experimental action route (`solve.py -actions`).
`action_prompt.assemble` (`solver/action_prompt.py`) builds the two system prompts
from them. The [action prompt interface](../../docs/encodings/action-prompts.md)
specifies what the prompts teach.

## Files

| file | content |
|---|---|
| `stage1_instructions.txt` | the action rules of Stage 1: readings, actions and their roles, modes, contexts, snapshots |
| `stage1_checklist.txt` | the final checks of a Stage-1 response |
| `stage2_instructions.txt` | the action rules of Stage 2: the envelope (`worlds`, `contexts`, `query_contexts`, `types`, `logic`), the law forms, the query packages |
| `stage2_checklist.txt` | the final checks of a Stage-2 response |
| `examples.json` | the 25 example translations that both prompts show |
| `routing_cases.json` | the 4 routing contrasts that the Stage-1 prompt shows |
| `manifest.json` | the SHA-256 of every source file, of each assembled prompt and of each rendered example block, and the prompt sizes in bytes |

## How a prompt is assembled

The system prompt of each stage has six parts, joined by blank lines:

1. `prompts/stageN_instructions_full.txt`, the ordinary instructions
2. `prompts/stageN_examples.txt`, the ordinary examples
3. `prompts/stageN_checklist_full.txt`, the ordinary checklist
4. `stageN_instructions.txt` of this directory
5. the examples, rendered from `examples.json` and `routing_cases.json`
6. `stageN_checklist.txt` of this directory

The action rules come after the ordinary rules. Where the two conflict, the
action rules say that they take precedence. A change to an ordinary prompt file
also changes the action prompts.

`action_prompt.render_examples` writes each record as one block:

```
Example <id>
Input:
<Stage 1: the record's text.  Stage 2: the record's Stage 1 as one-line JSON>
Output:
<the record's Stage 1 or Stage 2 as one-line JSON>
```

Every record goes into the Stage-1 prompt. A record with a `stage2` field also
goes into the Stage-2 prompt; the routing contrasts have no `stage2` field. The
JSON files are the only source of the examples. No text copy of an example
exists.

## The records

An example translation has these fields:

| field | content |
|---|---|
| `id` | the name of the example |
| `purpose` | what the example shows |
| `authorship` | who wrote the example, and when |
| `text` | the English text: the `raw` sentences of `stage1`, joined by spaces |
| `stage1` | the Stage-1 response: the list of sentence packages |
| `route` | the route that `action_prompt.select_route` chooses from the Stage-1 units |
| `stage2` | the Stage-2 response: the envelope |
| `expect` | the outcome of the compiler: `source` (`supported` or `unsupported`) and `queries` (`ready` or the query outcome), and for some records `reason`, `forms`, `excluded`, `root` or `query_reason` |
| `revision`, `rules`, `answer` | in the seven examples of revision I only: the revision, the labels of the rules that the example shows, and the answer on GK |

A routing contrast has the fields `id`, `purpose`, `authorship`, `text`, `route`
and `stage1`. Its `route` is `actions`, `ordinary` or `diagnostic`.

## Editing

The two JSON files follow the layout of `prompts/stage1_examples.txt` and
`prompts/stage2_examples.txt`:

- A list or dict without a nested list or dict is on one line.
- A nested list or dict is on one line when it fits in 100 columns.
- Otherwise each element or key is on its own line, indented by two spaces. A
  broken list keeps its leading strings and numbers on its first line, as in
  `["@id", "S1",`.

An edit of a file here changes the assembled prompt. `manifest.json` records
the hashes of the files and of the assembled prompts; `action_prompt.assemble()`
returns them.

The prompts are revision I. The revision name is in the first line of both
instructions files, in the bundle status that `action_prompt.assemble` returns
(`prompt revision I`), and in `manifest.json`.
