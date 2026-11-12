from pathlib import Path

T = """# server.N: N совпадает с номером в файле myid этого сервера
tickTime=2000
initLimit=10
syncLimit=5
dataDir=/data
dataLogDir=/datalog
clientPort={port}
admin.enableServer=false
quorumListenOnAllIPs=true
4lw.commands.whitelist=srvr,stat,ruok,mntr,conf
server.1=zk1:2888:3888
server.2=zk2:2889:3889
server.3=zk3:2890:3890
"""
for i, port in ((1, 2181), (2, 2182), (3, 2183)):
    p = Path(__file__).parent / ("zk%d" % i) / "zoo.cfg"
    p.write_text(T.format(port=port), encoding="utf-8", newline="\n")
    print("записано", p)