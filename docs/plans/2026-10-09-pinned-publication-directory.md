# Pinned private publication directory

Scope: amend only `atomic_private_bytes`, preserving bytes, modes and caller
contracts. Synthetic reproduction on main-based commit 0d4b978 replaces the
output parent with an input-directory symlink immediately before temporary-file
creation. The current path-based publisher replaces the synthetic configuration
and its inode. No private inputs or shared resources participate.

Open the output parent once with `O_RDONLY | O_DIRECTORY | O_NOFOLLOW` before
checking the destination or creating the temporary file. Use that descriptor for
destination lstat (`follow_symlinks=False`), exclusive temporary creation at 0600,
rename source/destination, directory fsync and temporary unlink. Preserve the
existing explicit symlink-destination refusal. Close all descriptors on failure;
never re-resolve the parent during publication or cleanup. Write and fsync the
complete bytes before rename; failure never reports success. A failure before
rename retains the previous destination and removes only this owned temporary.

This anchors publication to the parent actually opened. Renaming that parent
after acquisition cannot redirect publication or cleanup into another directory.
A symlink parent already present when opening is refused. This does not protect
against arbitrary same-user mutation before acquisition, changes to ancestors
before the parent is opened, input/destination replacement before caller collision
checks, or power loss beyond successful fsync guarantees. Existing caller
preservation checks and cooperative private-directory ownership remain required;
this is no claim of hostile administrator isolation or multi-file transactions.

Discriminating socket-forbidden tests: inject rename-and-symlink replacement
after directory acquisition and before exclusive temporary creation; assert
original config bytes and inode survive, new output remains in the pinned parent,
no temp leaks, output 0600 and correct directory fsync. Repeat on rename failure
to prove cleanup uses the pinned descriptor and previous output survives. Reject
pre-existing parent/destination symlinks. Existing preparation failure injection
must accept descriptor-relative rename kwargs while retaining its original
assertion. Run the required Python suite on correction branch and complete stack.

Blast radius: local private artifact publisher only, no remote operations. Design
requires exact-hash Astra approval before implementation. Rollback: revert the
scoped implementation commit; retained inputs/journals remain untouched. Commit
and publish a main-compatible PR, propagate using merges without rewriting, reply
to PR19 finding 4228954408, and leave all PRs open.
