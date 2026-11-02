"""Killable stage boundaries, including DNS and slow response headers."""
import multiprocessing


def _child(send, function, args):
    try: send.send((True,function(*args)))
    except BaseException: send.send((False,None))
    finally: send.close()


def bounded(function, args, seconds):
    if seconds <= 0: raise TimeoutError('Research deadline reached')
    context=multiprocessing.get_context('spawn')
    receive,send=context.Pipe(duplex=False)
    process=context.Process(target=_child,args=(send,function,args),daemon=True)
    process.start(); send.close()
    try:
        if not receive.poll(seconds): raise TimeoutError('Research stage timed out')
        ok,value=receive.recv()
        if not ok: raise ValueError('Research stage unavailable')
        return value
    finally:
        receive.close()
        if process.is_alive(): process.terminate()
        process.join(timeout=2)
        if process.is_alive(): process.kill(); process.join(timeout=2)
