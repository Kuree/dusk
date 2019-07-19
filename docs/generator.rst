.. _generator:

Generator of Generators
#######################

Kratos follows the idea of `generators of generators`. Every class
inherits from ``kratos.Generator`` class is a generator which can
generate different circuit based on different parameters. To push
the generator idea even further, you can modify the circuit even
after being instantiated from a generator class. The backend engine
can take of the additional changes.

There are two ways to populate circuit definition to the generator:

1. Free-style code block
2. Procedural code generation

Each approach has its own strengths and drawbacks. In general,
using code block makes the Python code more readable and
procedural code generation is more flexible and universal. If you
look at the source code, free-style code block is just a helper
to construct circuit definition procedurally.

Port and Variables
==================
As in verilog, we need to declare ports and variables before we can
describe the circuit logic. To declare a port, you can call the
``port`` function from the generator:

.. code-block:: Python

    def port(self, name: str, width: int, direction: PortDirection,
                port_type: PortType = PortType.Data,
                is_signed: bool = False)

``PortDirection`` and ``PortType`` are enums to specify the types of
the port we're creating. The definitions for these enum are:

.. code-block:: Python

    class PortDirection(enum.Enum):
        In = _kratos.PortDirection.In
        Out = _kratos.PortDirection.Out
        InOut = _kratos.PortDirection.InOut


    class PortType(enum.Enum):
        Data = _kratos.PortType.Data
        Clock = _kratos.PortType.Clock
        AsyncReset = _kratos.PortType.AsyncReset
        ClockEnable = _kratos.PortType.ClockEnable
        Reset = _kratos.PortType.Reset

Notice that ``_kratos`` is a namespace that came from the native C++ binding.

To declare a variable, simply call the following function to create one:

.. code-block:: Python

    def var(self, name: str, width: int,
             is_signed: bool = False)

kratos will do type checking for ``width``, ``port_type``, and ``is_signed``
to avoid any implicit conversion that could be difficult to detect.

Variable Proxies
----------------
For simple modules, it is fine to hold a port/variable/parameters as class
attributes. However, as the generator gets more complicated, it may be
difficult to maintain all the variable names. kratos ``Generator`` comes
with handy proxies to access all the variables you need. You can access a
port either through

- ``[gen].ports.port_name``
- ``[gen].ports["port_name"]``

where ``[gen]`` is any generator instance and ``port_name`` is the name you
want to access. Similarly, you can use

- ``[gen].vars.port_name``
- ``[gen].vars["port_name]``

and ``[gen].params`` for parameters.

Expressions
-----------

Whenever we perform some arithmetic or logic operator on port/variables, we
implicitly create an expression. An expression can be assigned to a port or
a variable. It can also be composed together to form more complex expressions.

.. code-block:: pycon

    >>> from kratos import *
    >>> g = Generator("mod")
    >>> a = g.var("a", 1)
    >>> b = g.var("b", 1)
    >>> c = a + b
    >>> c
    a + b
    >>> d = c + c
    >>> d
    (a + b) + (a + b)

To avoid conflicts with python built-in functions, some verilog operators
are not directly implemented as operator overloads in Python:

1. ``eq()`` for logical comparison
2. ``ashr()`` for signed arithmetic shift right.

Child generators
================

You can use `add_child_generator(inst_name, child)` to add a child
generator. The ``inst_name`` is the instance name for that child
generator and has to be unique within the parent scope. After adding
the child generator to the parent scope, you can access the child
generator through `self[inst_name]` method. ``__getitem__()``
has been overloaded to get the child.

This is a required step to properly instantiate the sub modules.

External Modules
================
kratos allows you to create either an external module or an stub.

External module
---------------
External modules are created from verilog source. You can call
``Generator.from_verilog`` to import verilog files. You need to
provide the port type mapping to alow the type checking to work
properly.

.. code-block:: Python

    def from_verilog(top_name: str, src_file: str, lib_files: List[str],
                        port_mapping: Dict[str, PortType]):

``lib_files`` lets you import related verilog files at once so
you don't have to copy these files over.

Stub module
-----------
Sometimes you're dealing with IPs while working on an open-source
project, you can create a stub that mimics the IP interface but
produce junk output. kratos provides helper methods to do that.
All you need to do is to set the module as a stub after declaring
the interface. ``self.is_stub = True``. The backend engine will
zero out the outputs for you.

Free-Style Code Block
=====================
kratos allows to write Genesis2 style verilog code inside Python (to
some extent). The basic principle is that if a Python expression can
be evaluated as integer or boolean, the compiler will be happy to do
so. If the Python code results in a kratos expression, the compiler
will leave it as is in the verilog.

Allowed python control flows that will be statically evaluated:

1. ``for``
2. ``if``
3. class function calls that returns a single statement

Keywords like ``while`` may or may not work depends on how it is nested
side other statements.

Please also notice that kratos don't allow ``generate`` statement in
verilog, so the for loop range has to be statically determined,
otherwise a ``SyntaxError`` will be thrown.

To add a code block to the generator definition, you need to wrap the
code block into a class method with only `self` as argument, then call
``[gen].add_code([func])`` to add the code block, where ``func`` is the
function wrapper.

Combinational and Sequential Code Block
---------------------------------------

If you need to add a sequential code block that depends on some signals,
you need to decorate the function wrapper with ``always`` and sensitivity
list. The list format is ``List[Tuple[EdgeType, str]]``, where the
``EdgeType`` can be either ``BlockEdgeType.Posedge`` or
``BlockEdgeType.Negedge``. The ``str`` has be either a port or variable
name. For instance, the code below will produce a code block that listens
to ``clk`` and ``rst`` signal.

.. code-block:: Python

    @always([(BlockEdgeType.Posedge, "clk"),
             (BlockEdgeType.Posedge, "rst")])
    def seq_code_block(self):
        # code here

You don't have to do anything with the combinational code block.

Examples
--------
Here are some examples the free-style code block in kratos.

.. code-block:: Python

    class AsyncReg(Generator):
    def __init__(self, width):
        super().__init__("register")

        # define inputs and outputs
        self._in = self.port("in", width, PortDirection.In)
        self._out = self.port("out", width, PortDirection.Out)
        self._clk = self.port("clk", 1, PortDirection.In, PortType.Clock)
        self._rst = self.port("rst", 1, PortDirection.In,
                              PortType.AsyncReset)
        self._val = self.var("val", width)

        # add combination and sequential blocks
        self.add_code(self.seq_code_block)

        self.add_code(self.comb_code_block)

    @always([(BlockEdgeType.Posedge, "clk"),
             (BlockEdgeType.Posedge, "rst")])
    def seq_code_block(self):
        if ~self._rst:
            self._val = 0
        else:
            self._val = self._in

    def comb_code_block(self):
        self._out = self._val

Here is the verilog produced:

.. code-block:: pycon

  >>> reg = AsyncReg(16)
  >>> mod_src = verilog(reg)
  >>> print(mod_src["register"]

.. code-block:: SystemVerilog

  module register (
    input logic  clk,
    input logic [15:0] in,
    output logic [15:0] out,
    input logic  rst
  );

  logic  [15:0] val;

  always @(posedge rst, posedge clk) begin
    if (~rst) begin
      val <= 16'h0;
    end
    else begin
      val <= in;
    end
  end
  always_comb begin
    out = val;
  end
  endmodule   // register

Here is another example on `for` static evaluation

.. code-block:: Python

    class PassThrough(Generator):
        def __init__(self, num_loop):
            super().__init__("PassThrough", True)
            self.in_ = self.port("in", 1, PortDirection.In)
            self.out_ = self.port("out", num_loop, PortDirection.Out)
            self.num_loop = num_loop

            self.add_code(self.code)

        def code(self):
            if self.in_ == self.const(1, 1):
                for i in range(self.num_loop):
                    self.out_[i] = 1
            else:
                for i in range(self.num_loop):
                    self.out_[i] = 0

Here is the generated verilog

.. code-block:: pycon

    >>> a = PassThrough(4)
    >>> mod_src = verilog(a)
    >>> print(mod_src["PassThrough"])

.. code-block:: SystemVerilog

  module PassThrough (
    input logic  in,
    output logic [3:0] out
  );

  always_comb begin
    if (in == 1'h1) begin
      out[0:0] = 1'h1;
      out[1:1] = 1'h1;
      out[2:2] = 1'h1;
      out[3:3] = 1'h1;
    end
    else begin
      out[0:0] = 1'h0;
      out[1:1] = 1'h0;
      out[2:2] = 1'h0;
      out[3:3] = 1'h0;
    end
  end
  endmodule   // PassThrough


Procedural code generation
==========================

Sometimes it is very difficult to generate a desired circuit definition through
limited free-style code block. If that is the case, you can use the procedural
code generation.

The main idea here is to construct verilog statement in a hierarchical way. The
hierarchy is defined by verilog's ``begin ... end`` closure. Here are a list
of statements you can construct:

- ``SequentialCodeBlock``
- ``CombinationalCodeBlock``
- ``SwitchStmt``
- ``IfStmt``
- ``AssignStmt``


.. note::
    kratos provides a helper function called `wire(var1, var2)` that wires
    things together in the top level. In most cases the ordering does matter:
    it's the same as ``assign var1 = var2;``. The only exception is when one
    of them is a port (not port slice though).

Examples
--------

Here is an example on how to build a ``case`` based N-input mux.

.. code-block:: Python

    class Mux(Generator):
        def __init__(self, height: int, width: int):
            name = "Mux_{0}_{0}".format(width, height)
            super().__init__(name)

            # pass through wires
            if height == 1:
                self.in_ = self.port("I", width, PortDirection.In)
                self.out_ = self.port("O", width, PortDirection.Out)
                self.wire(self.out_, self.in_)
                return

            self.sel_size = clog2(height)
            for i in range(height):
                self.port("I{0}".format(i), width, PortDirection.In)
            self.out_ = self.port("O", width, PortDirection.Out)
            self.port("S", self.sel_size, PortDirection.In)

            # add a case statement
            stmt = SwitchStmt(self.ports.S)
            for i in range(height):
                stmt.add_switch_case(self.const(i, self.sel_size),
                                    self.out_.assign(self.ports["I{0}".format(i)]))
            # add default
            stmt.add_switch_case(None, self.out_.assign(self.const(0, width)))
            comb = CombinationalCodeBlock(self)
            comb.add_stmt(stmt)

Here is the generated verilog

.. code-block:: SystemVerilog

  module Mux_16_16 (
    input logic [15:0] I0,
    input logic [15:0] I1,
    input logic [15:0] I2,
    output logic [15:0] O,
    input logic [1:0] S
  );

  always_comb begin
    case (S)
      default: begin
        O = 16'h0;
      end
      2'h0: begin
        O = I0;
      end
      2'h2: begin
        O = I2;
      end
      2'h1: begin
        O = I1;
      end
    endcase
  end
  endmodule   // Mux_16_16
