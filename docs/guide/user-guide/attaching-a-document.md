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
before anything is kept, and what a check of its text found under **Possible personal data or
secrets**: e-mail addresses, telephone numbers, NHS or National Insurance numbers, postcodes,
keys, tokens or passwords. It says what kind of thing it found and how sure it is, never what
it found. Remove what it lists from the file and choose the file again, or, if it should be kept,
such as a public contact address, tick that you have checked the document and select **Attach
anyway**. Finding nothing does not mean there is nothing: names and places are not looked for.
When you are content, select **Attach this document**. If you select **Cancel**, nothing is
attached.

The document then shows as a chip under the message box. Select its **Remove** button if you
change your mind. You can type a message as well, or send it on its own. A message can carry one
inventory and one document.

## Where it goes

The document is stored in your project, and anyone working on the project can read it.

When Data Director drafts a README or a data dictionary, the Documentation Editor reads the text
of the documents you attached, the latest first. Its AI model may then suggest answers to the
draft's questions from them, such as a field's unit that your field notes give, or how the
data were collected for the README's Methods section. Methods is suggested only from your
documents, never guessed from your files. A suggestion is
shown beside its question and is never written into the draft: it becomes part of the document
only when you save it, or a correction of it, as your answer. The outcome of the draft names the
documents the model was given, and says if one was too long to give in full.

The agent you are talking to, and every other agent, is told only each document's name, type and
size. The text goes to an AI model hosted outside your institution only if your institution's
deployment allows that; where it does not, drafts are made without it.

Your institution may choose not to keep attached documents at all. Then **Attach a file** takes
only an inventory, the note beneath it says that documents are not kept, and no agent is given a
document your project already holds. Give what the document says in your message instead.
