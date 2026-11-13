# Depositing your data

The Data Director gets your project ready to deposit. It does not deposit it for you. Once it has
built the deposit package, you publish your data in the repository you chose, by hand, using the
metadata you approved. This page explains how.

Data Director does not deposit, register a DOI or release an embargo. The repository does those
when you publish the item there. Depositing through a repository's own interface, after you
approve it, is planned (TODO(#383)).

## Before you start

In the project's **Deposit** tab:

1. Choose **Check the project**. The project is checked against what the repository you chose
   asks for. Anything listed under *Must be fixed before packaging* stops the package; fix it and
   check again.
2. Choose **Build the package**, then **Download the package**.

The **Repository** tab shows the repository you chose and the fields its form asks for.

## What the package is for

The package is the record of how your dataset was prepared. It holds:

- the documents you approved, including the metadata record;
- the record of who decided what, and when;
- how generative AI was used, and a disclosure statement;
- a list of your data files, each with its size and SHA-256 digest (a fingerprint).

Your data files are listed but not included. The package is not a file the repository reads or
imports: keep it with the project, and attach it to the item if the repository lets you and you
want it published alongside your data.

## Steps in the repository

The **Deposit** tab lists these steps once the package is built, with the details for the
repository you chose.

1. **Create the item.** Sign in to the repository and start a new item (a dataset, or the item
   type your data is).
2. **Enter the metadata.** Open the approved metadata record (in the package under `documents/`,
   or in the project's **Documents** tab) and copy each value into the repository's form. Where
   the deployment knows the repository's form, the Deposit tab names the form's fields, such as
   *Title*, *Authors* and *Keywords*, required ones first. A value the profile names no form field
   for can go wherever the form allows, or stay in the record.
3. **Attach your data files.** Upload the files the package lists. Their digests in the package
   show that the files you upload are the files that were described.
4. **Keep the package.** Store it with the project's records, or attach it to the item.
5. **Review and publish.** Check the item's preview, set any access restriction or embargo the
   repository offers, and publish it. The repository registers the DOI.

## ORDA

ORDA, the University of Sheffield's repository, runs on Figshare. The form labels the Deposit tab
shows for ORDA come from the deployment's profile of it, not from the app, so a steward can
correct them without a new release.

Some of what ORDA asks is not yet confirmed. The Deposit tab lists those items under *Not yet
confirmed for ORDA*; until they are settled, follow ORDA's own deposit form where it differs
(TODO(#385)).

## See also

- [The workflow](workflow.md), Phase 5: Deposit and submit
- [What the Data Director records](records.md)
