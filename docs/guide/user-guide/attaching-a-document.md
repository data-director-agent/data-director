# Attaching a document

Besides an [inventory](making-an-inventory.md), you can attach a document **about** your data
to a message: a sampling protocol, a codebook, a lab notebook page or a README you already have.
Data Director keeps it in your project.

## What to attach

- Plain text (`.txt`) or Markdown (`.md`) files, of at most 256 KB.
- Documents that describe how the data were made, what the variables mean or how the files are
  organised.

Never attach the data themselves, such as a CSV of measurements or interview transcripts, and
never attach anything that identifies a person. Data Director cannot tell a document from data,
so it relies on you to keep to this rule. To describe your data files, make an inventory instead.

## Attaching it in the app

On the conversation page, select **Attach a file** under the message box and choose the
document, or drop it onto the message box. The app shows you the document's name, size and text
before anything is kept. When you are content, select **Attach this document**. If you select
**Cancel**, nothing is attached.

The document then shows as a chip under the message box. Select its **Remove** button if you
change your mind. You can type a message as well, or send it on its own. A message can carry one
inventory and one document.

## Where it goes

The document is stored in your project, and anyone working on the project can read it. The
agent you are talking to is told the document's name, type and size, but not its text. If agents
are given its text in future, it will go to an AI model hosted outside your institution only if
your institution's deployment allows that.
