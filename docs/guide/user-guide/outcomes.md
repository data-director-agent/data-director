# Understanding outcomes

Every run ends in one of five outcomes.

| Outcome     | Meaning                                                         |
| ----------- | --------------------------------------------------------------- |
| `succeeded` | The agent returned a result, and the harness's checks passed.   |
| `abstained` | The agent declined to answer rather than guess.                 |
| `referred`  | The matter needs a person's judgement.                          |
| `failed`    | The run did not complete, or a check failed.                    |
| `suspended` | The run is paused until a stated condition is met.              |

Nothing in the Data Director produces `suspended` yet; the app can show it.

A failed grounding or source check turns a result into `failed`: see
[the five stages of a reply](conversation.md#the-five-stages-of-a-reply).

The app shows, with each outcome, what it means and what to do next.

A `referred` or `abstained` outcome is a point where a person can help. Your institution's data
stewards can be asked about it; what they can then see and do in your project is in the
[Data Steward's Guide](../steward-guide/working-in-a-project.md).

Beside such a run, **Ask a data steward** opens a short form: your note, and a list of what will be
shared, which you can narrow. Nothing is sent until you press **Send to a data steward**. You can
also ask at any time from the project panel or from any project page. Your request, its state and
the steward's replies then show in the project panel and in the conversation, where a steward's
message is marked **Data steward** with their name. You can withdraw a request while it is open,
reply when a steward asks you something, and re-open one that was resolved or handed back.

TODO(#250): link to the outcome vocabulary in the contract once the reference pages are settled.
