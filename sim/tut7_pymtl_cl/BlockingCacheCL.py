#=========================================================================
# BlockingCacheCL
#=========================================================================
# A simple CL model of a write-through, no write-allocate blocking cache
# with single-word cache lines.

from pymtl      import *
from pclib.ifcs import InValRdyBundle, OutValRdyBundle
from pclib.cl   import InValRdyQueueAdapter, OutValRdyQueueAdapter

from pclib.ifcs import MemMsg,    MemReqMsg,    MemRespMsg
from pclib.ifcs import MemMsg4B,  MemReqMsg4B,  MemRespMsg4B

#-------------------------------------------------------------------------
# CacheLine
#-------------------------------------------------------------------------
# Class to hold cache line state including valid bit, tag, data

class CacheLine( object ):

  def __init__( s ):
    s.valid = False
    s.tag   = Bits(27,0)
    s.data  = Bits(32,0)

#-------------------------------------------------------------------------
# BlockingCacheCL
#-------------------------------------------------------------------------

class BlockingCacheCL( Model ):

  def __init__( s ):

    # Only supports 4B cache and memory interfaces

    s.cache_ifc_dtypes = MemMsg4B()
    s.mem_ifc_dtypes   = MemMsg4B()

    # Interface

    s.cachereq    = InValRdyBundle  ( s.cache_ifc_dtypes.req  )
    s.cacheresp   = OutValRdyBundle ( s.cache_ifc_dtypes.resp )

    s.memreq      = OutValRdyBundle ( s.mem_ifc_dtypes.req  )
    s.memresp     = InValRdyBundle  ( s.mem_ifc_dtypes.resp )

    # Adapters to hold request/response messages

    s.cachereq_q  = InValRdyQueueAdapter  ( s.cachereq  )
    s.cacheresp_q = OutValRdyQueueAdapter ( s.cacheresp )

    s.memreq_q    = OutValRdyQueueAdapter ( s.memreq    )
    s.memresp_q   = InValRdyQueueAdapter  ( s.memresp   )

    # Cache array for eight cache lines

    s.cache       = [ CacheLine() for _ in range(8) ]

    # Extra state maintained while waiting for a memresp

    s.wait_bit  = False
    s.wait_addr = Bits(32,0)

    #---------------------------------------------------------------------
    # Tick
    #---------------------------------------------------------------------

    @s.tick_cl
    def tick():

      # Tick adapters

      s.cachereq_q.xtick()
      s.cacheresp_q.xtick()

      s.memreq_q.xtick()
      s.memresp_q.xtick()

      # Some constants to simplify the code

      s.READ  = s.cache_ifc_dtypes.req.TYPE_READ
      s.WRITE = s.cache_ifc_dtypes.req.TYPE_WRITE

      # We conservatively make sure that several conditions are true
      # before processing a cache request: (1) there must be a cache
      # request in the cachereq queue; (2) the memreq queue must not be
      # full; and (3) the cacheresp queue must not be full. Assuming
      # these conditions are met, we call the corresponding member
      # function to process the cache request.

      if not s.wait_bit and not s.cachereq_q.empty() \
                        and not s.memreq_q.full() \
                        and not s.cacheresp_q.full():

        cachereq = s.cachereq_q.deq()

        if   cachereq.type_ == s.WRITE : s.process_cachereq_write( cachereq )
        elif cachereq.type_ == s.READ  : s.process_cachereq_read ( cachereq )
        else                           : assert False

      # If there is a memory response, turn it into a cache response and
      # send it out the cache response interface. Note that we must make
      # sure that the cacheresp queue is not full. Assuming these
      # conditions are met, we call the corresponding member function to
      # process the memory response.

      if s.wait_bit and not s.memresp_q.empty() \
                    and not s.cacheresp_q.full():

        memresp = s.memresp_q.deq()

        if   memresp.type_ == s.WRITE : s.process_memresp_write( memresp )
        elif memresp.type_ == s.READ  : s.process_memresp_read ( memresp )
        else                          : assert False

  #-----------------------------------------------------------------------
  # process_cachereq_write
  #-----------------------------------------------------------------------
  # Since this is a write-through cache, we always send out a write
  # request to memory. We update the cache on a hit, but since this is a
  # no-write-allocate cache we never do a refill because of a write cache
  # request.

  def process_cachereq_write( s, cachereq ):

    # Check to see if we hit or miss in cache

    tag = cachereq.addr[5:32]
    idx = cachereq.addr[2:5]
    hit = s.cache[idx].valid and (s.cache[idx].tag == tag)

    # On a cache hit, update the corresponding data

    if hit:
      s.cache[idx].data = cachereq.data

    # Always send write request to main memory

    s.memreq_q.enq( cachereq )

    # Set wait bit so cache knows to wait for response message

    s.wait_bit = True

  #-----------------------------------------------------------------------
  # process_memresp_write
  #-----------------------------------------------------------------------

  def process_memresp_write( s, memresp ):

    # Send the cache response message

    s.cacheresp_q.enq( memresp )

    # Clear the wait bit so cache can start processing new cachereqs

    s.wait_bit = False

  #-----------------------------------------------------------------------
  # process_cachereq_read
  #-----------------------------------------------------------------------

  def process_cachereq_read( s, cachereq ):

    # Check to see if we hit or miss in cache

    tag = cachereq.addr[5:32]
    idx = cachereq.addr[2:5]
    hit = s.cache[idx].valid and (s.cache[idx].tag == tag)

    # On a cache hit, return data from cache

    if hit:

      cacheresp = s.cache_ifc_dtypes.resp
      cacheresp.type_  = s.cache_ifc_dtypes.resp.TYPE_READ
      cacheresp.opaque = cachereq.opaque
      cacheresp.len    = cachereq.len
      cacheresp.data   = s.cache[idx].data

      s.cacheresp_q.enq( cacheresp )

    # On a cache miss, send out refill request to main memory

    if not hit:

      s.memreq_q.enq( cachereq )

      # Set wait bit so cache knows to wait for response message. We
      # need to keep track of the address so we know what cacheline to
      # update when the memresp comes back.

      s.wait_bit  = True
      s.wait_addr = cachereq.addr

  #-----------------------------------------------------------------------
  # process_memresp_read
  #-----------------------------------------------------------------------

  def process_memresp_read( s, memresp ):

    # Update the cache with the refill data

    cache_line = CacheLine()
    cache_line.valid = True
    cache_line.tag   = s.wait_addr[5:32]
    cache_line.data  = memresp.data

    idx = s.wait_addr[2:5]

    s.cache[idx] = cache_line

    # Send the cache response message

    s.cacheresp_q.enq( memresp )

    # Clear the wait bit so cache can start processing new cachereqs

    s.wait_bit = False

  #-----------------------------------------------------------------------
  # line_trace
  #-----------------------------------------------------------------------

  def line_trace( s ):

    trace_strs = []
    for cache_line in s.cache:
      if not cache_line.valid:
        trace_strs.append(' '*7)
      else:
        trace_strs.append(str(cache_line.tag))

    return "({})".format( '|'.join(trace_strs) )

