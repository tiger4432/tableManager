# -*- coding: utf-8 -*-
"""A caught error said in one line that also says WHERE (총괄 10-20, 소유자 「이게 다 에러를 접어서 띄워서 모르잖아」).

`where(e)` - «p.py:7 in parse»: the frame it broke in, under any error that wraps it.
`told(e)`  - «<its sentence> (p.py:7 in parse)»: what a screen, a queue or a record keeps of it.
A log keeps the whole traceback (`exc_info=e`); inside a loop the line carries `told(e)` alone.
Only the standard library - every package of the server imports this.
"""
import os
import traceback


def where(error):
    """The file, line and function the error broke in, under any error that wraps it - or None when it was never raised."""
    root = error
    while root.__cause__ is not None or (root.__context__ is not None and not root.__suppress_context__):
        root = root.__cause__ or root.__context__
    frames = traceback.extract_tb(root.__traceback__) if root.__traceback__ is not None else []
    if not frames:
        return None
    return "%s:%d in %s" % (os.path.basename(frames[-1].filename), frames[-1].lineno, frames[-1].name)


def told(error):
    """The error's sentence (its type when it has none) and where it broke."""
    text = str(error).strip() or type(error).__name__
    at = where(error)
    return "%s (%s)" % (text, at) if at else text
