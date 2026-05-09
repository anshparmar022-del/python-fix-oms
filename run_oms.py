import os
import signal
import sys
import time
import logging
import quickfix as fix

os.chdir(os.path.dirname(os.path.abspath(__file__)))
from fix_engine.oms_app import application as oms_app


def shutdown(acceptor):
    # Stops the FIX acceptor and exits safely
    logger = logging.getLogger("OMS_SYSTEM")
    logger.info("Shutdown signal received. Stopping acceptor...")
    try:
        acceptor.stop()
        oms_app.shutdown()
    except Exception as e:
        logger.warning("Warning during stop: %s", e)
    sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    print("\n" + "=" * 80)
    print("  🚀 FIX OMS — Institutional Order Management System")
    print("  " + "─" * 76)
    print("  💎 Instance      : OMS-PRODUCTION-SRV-1")
    print("  🌐 Connectivity  : FIX.4.4 | Port 5001")
    print("  🏦 Multi-Client  : ENABLED (CLIENT1, CLIENT2, QFIXMESSENGER)")
    print("  🛡️  Risk Engine  : ACTIVE")
    print("  📈 Matching      : LiquidityBook-Symbol-Routing")
    print("=" * 80 + "\n")

    setts = fix.SessionSettings("config/oms.cfg")
    acceptor = fix.SocketAcceptor(
        oms_app, fix.MemoryStoreFactory(), setts, fix.FileLogFactory(setts)
    )
    acceptor.start()

    print("✨ [SYSTEM] FIX Engine initialized and listening...")
    signal.signal(signal.SIGINT, lambda s, f: shutdown(acceptor))
    signal.signal(signal.SIGTERM, lambda s, f: shutdown(acceptor))
    while True:
        time.sleep(1)
