#=========================================================================
# BlockingCacheCL_test.py
#=========================================================================

from __future__ import print_function

import pytest
import random
import struct

from pymtl      import *
from pclib.test import mk_test_case_table, run_sim
from pclib.test import TestSource, TestSink
from pclib.test import TestMemory

from pclib.ifcs import MemMsg,    MemReqMsg,    MemRespMsg
from pclib.ifcs import MemMsg4B,  MemReqMsg4B,  MemRespMsg4B
from pclib.ifcs import MemMsg16B, MemReqMsg16B, MemRespMsg16B

from BlockingCacheCL import BlockingCacheCL

#-------------------------------------------------------------------------
# TestHarness
#-------------------------------------------------------------------------

class TestHarness( Model ):

  def __init__( s, src_msgs, sink_msgs, stall_prob, latency,
                src_delay, sink_delay ):

    # Messge type

    cache_msgs = MemMsg4B()
    mem_msgs   = MemMsg4B()

    # Instantiate models

    s.src   = TestSource      ( cache_msgs.req,  src_msgs,  src_delay  )
    s.cache = BlockingCacheCL ()
    s.mem   = TestMemory      ( mem_msgs, 1, stall_prob, latency )
    s.sink  = TestSink        ( cache_msgs.resp, sink_msgs, sink_delay )

    # Connect

    s.connect( s.src.out,       s.cache.cachereq  )
    s.connect( s.sink.in_,      s.cache.cacheresp )

    s.connect( s.cache.memreq,  s.mem.reqs[0]     )
    s.connect( s.cache.memresp, s.mem.resps[0]    )

  def done( s ):
    return s.src.done and s.sink.done

  def line_trace(s ):
    return s.src.line_trace() + " " + s.cache.line_trace() + " " \
         + s.mem.line_trace() + " " + s.sink.line_trace()

#-------------------------------------------------------------------------
# make messages
#-------------------------------------------------------------------------

def req( type_, opaque, addr, len, data ):
  msg = MemReqMsg4B()

  if   type_ == 'rd': msg.type_ = MemReqMsg.TYPE_READ
  elif type_ == 'wr': msg.type_ = MemReqMsg.TYPE_WRITE

  msg.addr   = addr
  msg.opaque = opaque
  msg.len    = len
  msg.data   = data
  return msg

def resp( type_, opaque, len, data ):
  msg = MemRespMsg4B()

  if   type_ == 'rd': msg.type_ = MemRespMsg.TYPE_READ
  elif type_ == 'wr': msg.type_ = MemRespMsg.TYPE_WRITE

  msg.opaque = opaque
  msg.len    = len
  msg.data   = data
  return msg

#----------------------------------------------------------------------
# Test Case: basic
#----------------------------------------------------------------------

def basic_msgs( base_addr ):
  return [
    req( 'wr', 0x0, base_addr, 0, 0xdeadbeef ), resp( 'wr', 0x0, 0, 0          ),
    req( 'rd', 0x1, base_addr, 0, 0          ), resp( 'rd', 0x1, 0, 0xdeadbeef ),
  ]

#----------------------------------------------------------------------
# Test Case: basic_hit
#----------------------------------------------------------------------

def basic_hit_msgs( base_addr ):
  return [
    req( 'wr', 0x0, base_addr, 0, 0xdeadbeef ), resp( 'wr', 0x0, 0, 0          ),
    req( 'rd', 0x1, base_addr, 0, 0          ), resp( 'rd', 0x1, 0, 0xdeadbeef ),
    req( 'wr', 0x2, base_addr, 0, 0xdeadbeef ), resp( 'wr', 0x2, 0, 0          ),
    req( 'rd', 0x3, base_addr, 0, 0          ), resp( 'rd', 0x3, 0, 0xdeadbeef ),
    req( 'rd', 0x4, base_addr, 0, 0          ), resp( 'rd', 0x4, 0, 0xdeadbeef ),
    req( 'rd', 0x5, base_addr, 0, 0          ), resp( 'rd', 0x5, 0, 0xdeadbeef ),
    req( 'rd', 0x6, base_addr, 0, 0          ), resp( 'rd', 0x6, 0, 0xdeadbeef ),
  ]

#----------------------------------------------------------------------
# Test Case: stream
#----------------------------------------------------------------------

def stream_msgs( base_addr ):

  msgs = []
  for i in range(20):
    msgs.extend([
      req( 'wr', i, base_addr+4*i, 0, i ), resp( 'wr', i, 0, 0 ),
      req( 'rd', i, base_addr+4*i, 0, 0 ), resp( 'rd', i, 0, i ),
    ])

  return msgs

#----------------------------------------------------------------------
# Test Case: random
#----------------------------------------------------------------------

def random_msgs( base_addr ):

  rgen = random.Random()
  rgen.seed(0xa4e28cc2)

  vmem = [ rgen.randint(0,0xffffffff) for _ in range(20) ]
  msgs = []

  for i in range(20):
    msgs.extend([
      req( 'wr', i, base_addr+4*i, 0, vmem[i] ), resp( 'wr', i, 0, 0 ),
    ])

  for i in range(20):
    idx = rgen.randint(0,19)

    if rgen.randint(0,1):

      correct_data = vmem[idx]
      msgs.extend([
        req( 'rd', i, base_addr+4*idx, 0, 0 ), resp( 'rd', i, 0, correct_data ),
      ])

    else:

      new_data = rgen.randint(0,0xffffffff)
      vmem[idx] = new_data
      msgs.extend([
        req( 'wr', i, base_addr+4*idx, 0, new_data ), resp( 'wr', i, 0, 0 ),
      ])

  return msgs

#-------------------------------------------------------------------------
# Test Case Table
#-------------------------------------------------------------------------

test_case_table = mk_test_case_table([
  (                             "msg_func          stall lat src sink"),
  [ "basic",                     basic_msgs,       0.0,  0,  0,  0    ],
  [ "basic_hit",                 basic_hit_msgs,   0.0,  5,  0,  0    ],
  [ "stream",                    stream_msgs,      0.0,  0,  0,  0    ],
  [ "random",                    random_msgs,      0.0,  0,  0,  0    ],
  [ "random_3x14",               random_msgs,      0.0,  0,  3,  14   ],
  [ "stream_stall0.5_lat0",      stream_msgs,      0.5,  0,  0,  0    ],
  [ "stream_stall0.0_lat4",      stream_msgs,      0.0,  4,  0,  0    ],
  [ "stream_stall0.5_lat4",      stream_msgs,      0.5,  4,  0,  0    ],
  [ "random_stall0.5_lat4_3x14", random_msgs,      0.5,  4,  3,  14   ],
])

#-------------------------------------------------------------------------
# Test cases
#-------------------------------------------------------------------------

@pytest.mark.parametrize( **test_case_table )
def test_1port( test_params, dump_vcd ):
  msgs = test_params.msg_func(0x1000)
  run_sim( TestHarness( msgs[::2], msgs[1::2],
                        test_params.stall, test_params.lat,
                        test_params.src, test_params.sink ),
           dump_vcd )

