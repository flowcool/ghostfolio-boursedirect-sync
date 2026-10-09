# Pinned private publication directory — Astra design review

Date: 2026-10-09. Owner: `infra-4g8u.75`. Review scope: design only.

**Verdict: APPROVED** for the bounded design in
`docs/plans/2026-10-09-pinned-publication-directory.md`, exact SHA-256:

```text
5c700158790fc5c8c4c8138dfc55ddc6e7de30359716ad0af4fca694c38d6ed8
```

This is permission to pass the existing design gate, not implementation evidence,
PR review, merge approval or authorization for remote financial writes. No tests,
external requests, private inputs, Beads changes or Git changes were performed
by this reviewer. The only authored artifact is this report.

## Assessment

The current publisher creates, replaces and cleans temporary files through a
parent pathname that can resolve to different directories during one operation.
Opening the parent before any destination check or temporary creation, then
using that same descriptor for every namespace operation, addresses that defect.
The parent-swap reproduction described in the plan is consistent with the source;
its execution and observed bytes/inodes remain the implementing session's
evidence, not an independently repeated experiment in this review.

Approval requires basename-only source and destination arguments to descriptor-
relative operations: a full or absolute pathname could bypass the pinned parent.
The destination check must distinguish an absent entry from other stat failures
and preserve explicit refusal of an existing symlink, including a dangling one.
Exclusive creation must precede ownership of the temporary name: a failed
`O_EXCL` open must never lead to unlinking the pre-existing entry. All descriptor
ownership transitions, including failure to construct the file stream, must
close the descriptor exactly once. These are implementation obligations of the
plan's existing anchoring, refusal, ownership and failure requirements.

The narrow race claim is sound. After acquisition, moving the opened directory
or replacing its old path with a symlink cannot redirect descriptor-relative
creation, rename, unlink or directory fsync. `O_NOFOLLOW` protects the final
parent component at acquisition; it does not validate every ancestor. Caller
collision checks and cooperative private-directory ownership remain necessary.
This does not establish input preservation against arbitrary mutation between
caller validation and acquisition, nor against a hostile same-user process
changing entries inside the pinned directory. A destination symlink introduced
after the explicit check can have its entry replaced by rename without following
its referent; the design must not claim continuous symlink refusal or locking.

Before successful rename, write, file-fsync or rename failure must preserve the
previous destination and clean only an owned temporary entry in the pinned
directory. After successful rename, directory-fsync failure must propagate even
though the new destination may already be visible. It cannot imply restoration
of the previous file. This is consistent with the plan's explicitly pre-rename
preservation guarantee and the existing absence of multi-file transactions.

## Discriminating verification required before delivery

- Swap the parent immediately before exclusive temporary creation, after its
  descriptor has been acquired. Preserve synthetic input bytes **and inode**;
  assert the new bytes and mode 0600 in the moved original directory, with no
  publication or temporary entry under the replacement input directory.
- Identify the directory passed to fsync by descriptor identity (`fstat` device
  and inode), not by the old pathname. Assert file fsync precedes rename and the
  pinned directory fsync follows successful rename.
- Repeat the swap with injected rename failure. Assert previous output and
  input bytes/inodes survive, cleanup reaches the moved directory, and the
  replacement directory remains unchanged. Merely checking the old output
  pathname for temporary files would miss a leak.
- Cover pre-existing parent symlinks and destination symlinks, including
  dangling destinations. Inject exclusive-create failure to prove a colliding
  temporary entry is not removed, and pre-rename persistence failure to exercise
  owned cleanup and descriptor closure. Directory-fsync failure must report
  failure without asserting that rename was rolled back.
- Adapt the existing preparation failure injection to descriptor-relative
  rename keyword arguments while continuing to target the output publication,
  not an earlier journal write. Preserve its previous-artifact and journal
  assertions. Run the required socket-forbidden Python suite on the correction
  branch and complete stack; this review supplies no passing-test claim.

Rollback by reverting the scoped implementation is coherent for a local
publisher change and does not require rewriting retained inputs or journals.
The plan's publication and propagation steps remain governed by the parent
session's user authorization; all PRs must remain open.

Knowledge verdict: **Used and sufficient**. The narrow indexed Ghostfolio lookup
reached the current `saved-input-report-preservation.md` concept and confirmed
that output preservation is separate from captured hashes and transport method.
Its pinned evidence is not generalized into protection against directory races;
the current source and this plan govern the new boundary. No new operational
experiment was performed by the reviewer and no corpus mutation is needed here.
