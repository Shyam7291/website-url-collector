Every loop below is guarded by an explicit ceiling AND a visited/signature set,
so no code path can spin forever. What changed is that the same bounded budget
is now spent far more intelligently (see CHANGELOG at the bottom of this file).
"""
