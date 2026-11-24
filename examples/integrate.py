"""Contoh integrasi ke AI services kamu. Router fallback TIDAK diubah."""
import asyncio, signal, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ac import Config, Kernel, ACBridge, YourRouterAdapter, EchoRouter


async def nadi_loop(kernel, stop):
    while not stop.is_set():
        dt = kernel.heart.next_dt(kernel.affect.emotion[1], kernel.intero.h[5])
        try:
            await asyncio.wait_for(stop.wait(), timeout=dt)
            break
        except asyncio.TimeoutError:
            pass
        kernel.tick(activity=0.05)
        if kernel.heart.beats % 200 == 0:
            kernel.save()
        if kernel.dreamer.sleep.should_sleep(kernel.t):
            await kernel.dreamer.sleep_cycle(cycles=3)
            kernel.save()


async def main():
    cfg = Config.load("ac_config.json")
    kernel = Kernel(cfg)          # outreach tetap OFF
    kernel.restore()

    router = EchoRouter()         # ganti: YourRouterAdapter(router_kamu, tier_fn=...)
    bridge = ACBridge(kernel, router, use_llm_appraisal=False)

    stop = asyncio.Event()
    try:
        loop = asyncio.get_running_loop()
        for s in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(s, stop.set)
    except (NotImplementedError, AttributeError):
        pass

    task = asyncio.create_task(nadi_loop(kernel, stop))
    try:
        for msg in ["halo", "bagus makasih", "tolong jelaskan arsitektur", "aku kecewa"]:
            r = await bridge.handle(msg, contact="u_demo", confidence=0.7)
            print(r["mood"], r["focus"], r["action"], "->", r["text"][:80])
            await asyncio.sleep(0.2)
        await asyncio.sleep(1.0)
    finally:
        stop.set()
        await task
        kernel.save()             # WAJIB: manifest + contacts tersinkron
        print("shutdown bersih. chain:", kernel.mem.verify_chain())


if __name__ == "__main__":
    asyncio.run(main())
