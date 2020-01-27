import ast
import textwrap
import inspect
import astor
import _kratos
from .util import print_src
from _kratos import get_frame_local
import copy
import os
import enum


def __pretty_source(source):
    return "".join(source)


class LogicOperatorVisitor(ast.NodeTransformer):
    def __init__(self, local, global_, filename, scope_ln):
        self.local = local
        self.global_ = global_
        self.filename = filename
        self.scope_ln = scope_ln

    def get_file_line(self, ln):
        ln += self.scope_ln
        with open(self.filename) as f:
            lines = f.readlines()
        return lines[ln - 2]

    @staticmethod
    def concat_ops(func_name, values):
        # this is a recursive call
        assert len(values) > 0
        if len(values) == 1:
            return values[0]
        node = ast.Call(func=ast.Attribute(attr=func_name, value=values[0],
                                           cts=ast.Load()),
                        args=[values[1]], keywords=[])
        values = [node] + values[2:]
        return LogicOperatorVisitor.concat_ops(func_name, values)

    def check_var(self, var):
        r = eval(astor.to_source(var), self.local, self.global_)
        if not isinstance(r, _kratos.Var):
            raise SyntaxError("Cannot mix kratos variable with normal Python values in logical ops",
                              [self.filename, self.scope_ln + var.lineno,
                               var.col_offset, self.get_file_line(var.lineno)])

    def visit_BoolOp(self, node):
        # convert the bool op into a logical function
        # we don't allow mixing bool ops with normal python values and kratos values
        if isinstance(node.op, ast.And):
            # it's an and
            values = node.values
            for i in range(len(values)):
                values[i] = self.visit(values[i])
                self.check_var(values[i])
            return self.concat_ops("and_", values)
        elif isinstance(node.op, ast.Or):
            # it's an or
            values = node.values
            for i in range(len(values)):
                values[i] = self.visit(values[i])
            # the same as and
            return self.concat_ops("or_", values)
        else:
            raise SyntaxError("Invalid logical operator", (self.filename,
                                                           self.scope_ln + node.lineno,
                                                           node.col_offset,
                                                           self.get_file_line(node.lineno)))

    def visit_UnaryOp(self, node):
        if isinstance(node.op, ast.Not):
            return ast.Call(func=ast.Attribute(attr="r_not", value=node.operand,
                                               cts=ast.Load()),
                            args=[], keywords=[])
        return node


class StaticElaborationNodeVisitor(ast.NodeTransformer):
    class NameVisitor(ast.NodeTransformer):
        def __init__(self, target, value):
            self.target = target
            self.value = value

        def visit_Name(self, node):
            if node.id == self.target.id:
                if isinstance(self.value, int):
                    return ast.Constant(value=self.value, lineno=node.lineno)
                else:
                    return ast.Str(s=self.value, lineno=node.lineno)
            return node

    def __init__(self, generator, fn_src, local, global_, filename, func_ln):
        super().__init__()
        self.generator = generator
        self.fn_src = fn_src
        self.local = local.copy()
        self.global_ = global_.copy()
        self.local["self"] = self.generator
        self.target_node = {}

        self.filename = filename
        self.scope_ln = func_ln

        self.key_pair = []

    def visit_For(self, node: ast.For):
        # making sure that we don't have for/else case
        if len(node.orelse) > 0:
            # this is illegal syntax
            lines = [n.lineno for n in node.orelse]
            print_src(self.fn_src, lines)
            raise SyntaxError("Illegal Syntax: you are not allowed to use "
                              "for/else in code block")
        # get the target
        iter_ = node.iter
        iter_src = astor.to_source(iter_)
        try:
            iter_obj = eval(iter_src, self.global_, self.local)
            iter_ = list(iter_obj)
        except RuntimeError:
            print_src(self.fn_src, node.iter.lineno)
            raise SyntaxError("Unable to statically evaluate loop iter")
        for v in iter_:
            if not isinstance(v, (int, str)):
                print_src(self.fn_src, node.iter.lineno)
                raise SyntaxError("Loop iter has to be either integer or "
                                  "string, got " + str(type(v)))
        target = node.target
        if not isinstance(target, ast.Name):
            print_src(self.fn_src, node.iter.lineno)
            raise SyntaxError("Unable to parse loop "
                              "target " + astor.to_source(target))
        new_node = []
        for value in iter_:
            loop_body = copy.deepcopy(node.body)
            for n in loop_body:
                # need to replace all the reference to
                visitor = StaticElaborationNodeVisitor.NameVisitor(target, value)
                n = visitor.visit(n)
                self.key_pair.append((target.id, value))
                n = self.visit(n)
                self.key_pair.pop(len(self.key_pair) - 1)

                if isinstance(n, list):
                    for n_ in n:
                        new_node.append(n_)
                        self.target_node[n_] = (target.id, value)
                else:
                    new_node.append(n)
                    self.target_node[n] = (target.id, value)
        return new_node

    def __change_if_predicate(self, node):
        if isinstance(node, ast.UnaryOp):
            # notice that if the user uses `not var`, due to Python
            # implementation, it will return True/False, we need to
            # change that into r_not call
            if isinstance(node.op, ast.Not):
                target = node.operand
                target_src = astor.to_source(target)
                target_eval = eval(target_src, self.local)
                if isinstance(target_eval, _kratos.Var):
                    return ast.Call(func=ast.Attribute(value=target,
                                                       attr="r_not",
                                                       cts=ast.Load()),
                                    args=[], keywords=[], ctx=ast.Load())
            else:
                return node
        elif not isinstance(node, ast.Compare):
            return node
        op = node.ops[0]
        if not isinstance(op, ast.Eq):
            return node
        left = node.left
        left_src = astor.to_source(left)
        left_val = eval(left_src, self.local)
        if isinstance(left_val, _kratos.Var):
            # change it into a function all
            return ast.Call(func=ast.Attribute(value=left,
                                               attr="eq",
                                               cts=ast.Load()),
                            args=node.comparators,
                            keywords=[],
                            ctx=ast.Load)
        return node

    def visit_If(self, node: ast.If):
        predicate = node.test
        # if it's a var comparison, we change it to eq functional call
        predicate = self.__change_if_predicate(predicate)
        # we only replace stuff if the predicate has something to do with the
        # verilog variable
        predicate_src = astor.to_source(predicate)
        has_var = False
        try:
            predicate_value = eval(predicate_src, self.global_, self.local)
        except _kratos.exception.InvalidConversionException:
            has_var = True
            predicate_value = None

        # if's a kratos var, we continue
        if not has_var and not isinstance(predicate_value, _kratos.Var):
            if not isinstance(predicate_value, bool):
                print_src(self.fn_src, predicate.lineno)
                raise Exception("Cannot statically evaluate if predicate")
            if predicate_value:
                for i, n in enumerate(node.body):
                    if_exp = StaticElaborationNodeVisitor(self.generator, self.fn_src,
                                                          self.local, self.global_, self.filename,
                                                          self.scope_ln)
                    node.body[i] = if_exp.visit(n)
                return node.body
            else:
                for i, n in enumerate(node.orelse):
                    if_exp = StaticElaborationNodeVisitor(self.generator, self.fn_src,
                                                          self.local, self.global_, self.filename,
                                                          self.scope_ln)
                    node.orelse[i] = if_exp.visit(n)
                return node.orelse
        else:
            # need to convert the logical operators to either reduced function calls, or
            # expression or
            if_test = LogicOperatorVisitor(self.local, self.global_, self.filename, self.scope_ln)
            predicate = if_test.visit(node.test)

        expression = node.body
        else_expression = node.orelse

        if self.generator.debug:
            keywords_if = [ast.keyword(arg="f_ln",
                                       value=ast.Constant(value=node.lineno))]
            # do our best guess
            if len(else_expression) > 0:
                if else_expression[0].lineno != expression[0].lineno:
                    ln = else_expression[0].lineno + 1
                else:
                    ln = else_expression[0].lineno
                keywords_else = [ast.keyword(arg="f_ln",
                                             value=ast.Constant(value=ln))]
            else:
                keywords_else = []
        else:
            keywords_if = []
            keywords_else = []
        for key, value in self.key_pair:
            keywords_if.append(ast.keyword(arg=key, value=ast.Str(s=value)))

        if_node = ast.Call(func=ast.Attribute(value=ast.Name(id="scope",
                                                             ctx=ast.Load()),
                                              attr="if_",
                                              cts=ast.Load()),
                           args=[predicate] + expression,
                           keywords=keywords_if,
                           ctx=ast.Load)
        else_node = ast.Call(func=ast.Attribute(attr="else_", value=if_node,
                                                cts=ast.Load()),
                             args=else_expression, keywords=keywords_else)

        return self.visit(ast.Expr(value=else_node))


class AugAssignNodeVisitor(ast.NodeTransformer):
    def visit_AugAssign(self, node):
        # change any aug assign to normal assign
        return ast.Assign(targets=[node.target],
                          value=ast.BinOp(left=node.target, op=node.op,
                                          right=node.value),
                          lineno=node.lineno)


class AssignNodeVisitor(ast.NodeTransformer):
    def __init__(self, generator, debug):
        super().__init__()
        self.generator = generator
        self.debug = debug

    def visit_Assign(self, node):
        if len(node.targets) > 1:
            raise SyntaxError("tuple unpacking not allowed. got " +
                              astor.to_source(node))
        args = node.targets[:] + [node.value]
        if self.debug:
            args.append(ast.Constant(value=node.lineno))
        return ast.Expr(
            value=ast.Call(func=ast.Attribute(
                value=ast.Name(id="scope",
                               ctx=ast.Load()),
                attr="assign",
                cts=ast.Load()),
                args=args,
                keywords=[]))


class AssertNodeVisitor(ast.NodeTransformer):
    def __init__(self, generator, debug):
        super().__init__()
        self.generator = generator
        self.debug = debug

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "assert_":
            # we need to transform it to scope.assert_()
            args = node.args
            if self.debug:
                args.append(ast.Constant(value=node.lineno))
            return ast.Call(func=ast.Attribute(
                value=ast.Name(id="scope", ctx=ast.Load()),
                attr="assert_",
                cts=ast.Load()),
                args=args,
                keywords=[])
        return node


class ExceptionNodeVisitor(ast.NodeTransformer):
    def __init__(self, generator, debug):
        super().__init__()
        self.generator = generator
        self.debug = debug

    def visit_Raise(self, node: ast.Raise):
        func = node.exc
        if not isinstance(func, ast.Call):
            raise SyntaxError(astor.to_source(node) + " not supported")
        name = func.func
        if not isinstance(name, ast.Name):
            raise SyntaxError(astor.to_source(node) + " not supported")
        if name.id != "Exception":
            raise SyntaxError(astor.to_source(node) + " not supported")
        # change it to assert 0
        args = [ast.Constant(0)]
        if self.debug:
            args.append(ast.Constant(value=node.lineno))
        return ast.Call(func=ast.Attribute(
            value=ast.Name(id="scope", ctx=ast.Load()),
            attr="assert_",
            cts=ast.Load()),
            args=args,
            keywords=[])


class ReturnNodeVisitor(ast.NodeTransformer):
    def __init__(self, scope_name, debug=False):
        self.scope_name = scope_name
        self.debug = debug

    def visit_Return(self, node: ast.Return):
        value = node.value
        args = [value]
        if self.debug:
            args.append(ast.Constant(value=node.lineno))

        return ast.Expr(value=ast.Call(func=ast.Attribute(
            value=ast.Name(id=self.scope_name,
                           ctx=ast.Load()),
            attr="return_",
            cts=ast.Load()),
            args=args,
            keywords=[]))


class GenVarLocalVisitor(ast.NodeTransformer):
    def __init__(self, key, value, scope_name):
        self.key = key
        self.value = value
        self.scope_name = scope_name

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Attribute):
            attr = node.func
            insert_keywords = False
            if attr.attr == "assign" and \
                    isinstance(attr.value, ast.Name) \
                    and attr.value.id == self.scope_name:
                insert_keywords = True
            if insert_keywords:
                keyword = ast.keyword(arg=self.key,
                                      value=ast.Str(s=self.value))
                node.keywords.append(keyword)

        return node


def add_scope_context(stmt, _locals):
    for key, value in _locals.items():
        if isinstance(value, (int, float, str, bool)):
            # this is straight forward one
            stmt.add_scope_variable(key, str(value), False)
        elif isinstance(value, _kratos.Var) and len(value.name) > 0:
            # it's a var
            stmt.add_scope_variable(key, value.name, True)


class Scope:
    def __init__(self, generator, filename, ln, add_local):
        self.stmt_list = []
        self.generator = generator
        self.filename = filename
        if self.filename:
            assert os.path.isfile(self.filename)
        self.ln = ln
        self.add_local = add_local

        self._level = 0

    def if_(self, target, *args, f_ln=None, **kargs):
        add_local = self.add_local

        class IfStatement:
            def __init__(self, scope):
                self._if = _kratos.IfStmt(target)
                if f_ln is not None:
                    fn_ln = (scope.filename, f_ln + scope.ln - 1)
                    target.add_fn_ln(fn_ln, True)
                    self._if.add_fn_ln(fn_ln, True)
                    self._if.then_body().add_fn_ln(fn_ln, True)
                    # this is additional info passed in
                    if add_local:
                        add_scope_context(self._if, kargs)

                self.scope = scope
                for stmt in args:
                    if hasattr(stmt, "stmt"):
                        stmt = stmt.stmt()
                    self._if.add_then_stmt(stmt)

            def else_(self, *_args, f_ln=None):
                for stmt in _args:
                    if hasattr(stmt, "stmt"):
                        self._if.add_else_stmt(stmt.stmt())
                    else:
                        self._if.add_else_stmt(stmt)
                if f_ln is not None:
                    fn_ln = (self.scope.filename, f_ln + self.scope.ln - 1)
                    self._if.else_body().add_fn_ln(fn_ln, True)
                return self

            def stmt(self):
                return self._if

            def add_scope_variable(self, name, value, is_var=False):
                self._if.add_scope_variable(name, value, is_var)

        if_stmt = IfStatement(self)
        return if_stmt

    def assign(self, a, b, f_ln=None, **kargs):
        assert isinstance(a, _kratos.Var)
        try:
            stmt = a.assign(b)
        except _kratos.exception.VarException as ex:
            if f_ln is not None:
                print_src(self.filename, f_ln + self.ln - 1)
            # re-throw it
            raise ex
        if self.generator.debug:
            assert f_ln is not None
            stmt.add_fn_ln((self.filename, f_ln + self.ln - 1), True)
            if self.add_local:
                # obtain the previous call frame info
                __local = get_frame_local()
                add_scope_context(stmt, __local)
                # this is additional info passed in
                add_scope_context(stmt, kargs)
        return stmt

    def assert_(self, value, f_ln=None, **kargs):
        assert isinstance(value, (_kratos.Var, int))
        if isinstance(value, int):
            assert value == 0
            value = _kratos.constant(0, 1, False)
        stmt = _kratos.AssertValueStmt(value)
        if self.generator.debug:
            stmt.add_fn_ln((self.filename, f_ln + self.ln - 1), True)
            if self.add_local:
                # obtain the previous call frame info
                __local = get_frame_local()
                add_scope_context(stmt, __local)
                # this is additional info passed in
                add_scope_context(stmt, kargs)
        return stmt

    def add_stmt(self, stmt):
        self.stmt_list.append(stmt)

    def statements(self):
        return self.stmt_list


class FuncScope(Scope):
    def __init__(self, generator, func_name, filename, ln):
        super().__init__(generator, filename, ln, generator.debug)
        if generator is not None:
            self.__func = generator.internal_generator.function(func_name)

        self.__var_ordering = {}

    def input(self, var_name, width, is_signed=False) -> _kratos.Var:
        return self.__func.input(var_name, width, is_signed)

    def return_(self, value, f_ln=None):
        stmt = self.__func.return_stmt(value)
        if f_ln is not None:
            stmt.add_fn_ln((self.filename, f_ln + self.ln - 1), True)
        return stmt


def add_stmt_to_scope(fn_body):
    for i in range(len(fn_body.body)):
        node = fn_body.body[i]
        fn_body.body[i] = ast.Expr(
            value=ast.Call(func=ast.Attribute(
                value=ast.Name(id="scope",
                               ctx=ast.Load()),
                attr="add_stmt",
                cts=ast.Load()),
                args=[node],
                keywords=[]))


def __ast_transform_blocks(generator, func_tree, fn_src, fn_name, insert_self,
                           filename, func_ln,
                           transform_return=False, pre_locals=None):
    # pre-compute the frames
    # we have 3 frames back
    f = inspect.currentframe().f_back.f_back.f_back
    # will go one above to get the locals as well?
    if f.f_back is not None:
        _locals = f.f_back.f_locals.copy()
    else:
        _locals = {}
    _locals.update(f.f_locals)
    _globals = f.f_globals.copy()

    if pre_locals is not None:
        _locals.update(pre_locals)

    debug = generator.debug
    fn_body = func_tree.body[0]

    func_args = fn_body.args.args
    # add out scope to the arg list to capture all the statements
    func_args.append(ast.arg(arg="scope", annotation=None))

    if transform_return:
        return_visitor = ReturnNodeVisitor("scope", generator.debug)
        return_visitor.visit(fn_body)

    # transform aug assign
    aug_assign_visitor = AugAssignNodeVisitor()
    fn_body = aug_assign_visitor.visit(fn_body)

    # transform assign
    assign_visitor = AssignNodeVisitor(generator, debug)
    fn_body = assign_visitor.visit(fn_body)
    ast.fix_missing_locations(fn_body)

    # static eval for loop and if statement
    static_visitor = StaticElaborationNodeVisitor(generator, fn_src, _locals,
                                                  _globals, filename, func_ln)
    fn_body = static_visitor.visit(fn_body)

    # transform the assert_ function to get fn_ln
    assert_visitor = AssertNodeVisitor(generator, debug)
    fn_body = assert_visitor.visit(fn_body)
    exception_visitor = ExceptionNodeVisitor(generator, debug)
    fn_body = exception_visitor.visit(fn_body)

    # mark the local variables
    target_nodes = static_visitor.target_node
    for node, (key, value) in target_nodes.items():
        assign_local_visitor = GenVarLocalVisitor(key, value, "scope")
        assign_local_visitor.visit(node)

    # add stmt to the scope
    add_stmt_to_scope(fn_body)

    # add code to run it
    if insert_self:
        args = [ast.Name(id="_self", ctx=ast.Load())]
    else:
        args = []
    args.append(ast.Name(id="_scope", ctx=ast.Load()))
    call_node = ast.Call(func=ast.Name(id=fn_name, ctx=ast.Load()),
                         args=args,
                         keywords=[],
                         ctx=ast.Load
                         )
    func_tree.body.append(ast.Expr(value=call_node))
    return _locals, _globals


def inject_import_code(code_src):
    line1 = "import kratos"
    line2 = "from kratos import *"
    return "\n".join([line1, line2, code_src])


class CodeBlockType(enum.Enum):
    Sequential = enum.auto()
    Combinational = enum.auto()
    Initial = enum.auto()


class AlwaysWrapper:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args, **kwargs):
        raise SyntaxError("always block cannot be called normally. "
                          "Please do self.add_block()")


def transform_stmt_block(generator, fn, fn_ln=None):
    if callable(fn) or isinstance(fn, AlwaysWrapper):
        if isinstance(fn, AlwaysWrapper):
            fn = fn.fn
        else:
            import warnings
            warnings.warn("Bare function code as always block will be "
                          "deprecated soon. Please use @always_ff or "
                          "@always_comb", SyntaxWarning)
            print_src(get_fn(fn), get_ln(fn))
        fn_src = inspect.getsource(fn)
        fn_name = fn.__name__
        func_tree = ast.parse(textwrap.dedent(fn_src))
    else:
        assert isinstance(fn, ast.FunctionDef)
        # user directly passed in ast nodes
        assert fn_ln is not None
        fn_name = fn.name
        func_tree = ast.Module(body=[fn])
        fn_src = astor.to_source(fn)

    fn_body = func_tree.body[0]
    # needs debug
    debug = generator.debug
    store_local = debug and fn_ln is None
    filename = get_fn(fn) if fn_ln is None else fn_ln[0]
    ln = get_ln(fn) if fn_ln is None else fn_ln[1]

    # extract the sensitivity list from the decorator
    blk_type, sensitivity = extract_sensitivity_from_dec(fn_body.decorator_list,
                                                         fn_name)
    # remove the decorator
    fn_body.decorator_list = []
    # check the function args. it should only has one self now
    func_args = fn_body.args.args
    assert len(func_args) <= 1, \
        "statement block {0} has ".format(fn_name) + \
        "to be defined as def {0}(self) or {0}()".format(fn_name)
    insert_self = len(func_args) == 1

    _locals, _globals = __ast_transform_blocks(generator, func_tree, fn_src,
                                               fn_name,
                                               insert_self, filename, ln)

    src = astor.to_source(func_tree, pretty_source=__pretty_source)
    src = inject_import_code(src)
    code_obj = compile(src, "<ast>", "exec")

    # notice that this ln is an offset
    scope = Scope(generator, filename, ln, store_local)
    _locals.update({"_self": generator, "_scope": scope})
    _globals.update(_locals)
    exec(code_obj, _globals)
    stmts = scope.statements()
    return blk_type, sensitivity, stmts


def transform_function_block(generator, fn, arg_types):
    fn_src = inspect.getsource(fn)
    fn_name = fn.__name__
    func_tree = ast.parse(textwrap.dedent(fn_src))
    fn_body = func_tree.body[0]
    # needs debug
    debug = generator.debug

    # remove the decorator
    fn_body.decorator_list = []

    # check the function args. it should only has one self now
    func_args = fn_body.args.args
    insert_self = func_args[0].arg == "self"
    # only keep self
    fn_body.args.args = [func_args[0]]
    # add function args now
    filename = get_fn(fn)
    ln = get_ln(fn)
    scope = FuncScope(generator, fn_name, filename, ln)
    # add var creations
    arg_order = extract_arg_name_order_from_ast(func_args)
    var_body = declare_var_definition(arg_types, arg_order)
    var_src = astor.to_source(ast.Module(body=var_body))
    pre_locals = {"_scope": scope}
    var_code_obj = compile(var_src, "<ast>", "exec")
    exec(var_code_obj, pre_locals)
    _locals, _globals = __ast_transform_blocks(generator, func_tree, fn_src,
                                               fn_name, insert_self,
                                               filename, ln,
                                               transform_return=True,
                                               pre_locals=pre_locals)

    src = astor.to_source(func_tree)
    src = inject_import_code(src)
    code_obj = compile(src, "<ast>", "exec")

    _locals.update({"_self": generator, "_scope": scope})
    _globals.update(_locals)
    exec(code_obj, _globals)
    stmts = scope.statements()
    return arg_order, stmts


def declare_var_definition(var_def, arg_order):
    body = []
    for idx, name in arg_order.items():
        width, is_signed = var_def[idx]
        body.append(ast.Assign(targets=[ast.Name(id=name)],
                               value=ast.Call(func=ast.Attribute(
                                   value=ast.Name(id="_scope",
                                                  ctx=ast.Load()),
                                   attr="input",
                                   cts=ast.Load()),
                                   args=[ast.Str(s=name),
                                         ast.Constant(value=width),
                                         ast.NameConstant(value=is_signed)],
                                   keywords=[])))
    return body


def extract_arg_name_order_from_ast(func_args):
    result = {}
    for idx, arg in enumerate(func_args):
        if arg.arg != "self":
            result[len(result)] = arg.arg
    return result


def extract_arg_name_order_from_fn(fn):
    fn_src = inspect.getsource(fn)
    func_tree = ast.parse(textwrap.dedent(fn_src))
    fn_body = func_tree.body[0]
    func_args = fn_body.args.args
    return extract_arg_name_order_from_ast(func_args)


def extract_sensitivity_from_dec(deco_list, fn_name):
    if len(deco_list) == 0:
        return CodeBlockType.Combinational, []
    else:
        assert len(deco_list) == 1, \
            "{0} is not called with multiple decorators blocks".format(fn_name)
        call_obj = deco_list[0]
        if isinstance(call_obj, ast.Call):
            call_name = call_obj.func.id
        else:
            assert isinstance(call_obj, ast.Name), "Unrecognized " \
                                                   "function " \
                                                   "decorator {0}".format(call_obj)
            call_name = call_obj.id
        if call_name == "always_comb":
            return CodeBlockType.Combinational, []
        elif call_name == "initial":
            return CodeBlockType.Initial, []
        else:
            assert call_name == "always_ff", "Unrecognized function " \
                                             "decorator {0}".format(call_name)
        blk_type = CodeBlockType.Sequential
        raw_sensitivity = call_obj.args
        result = []
        # TODO: fix me. the frame num calculation is a hack
        local = get_frame_local(4)
        for entry in raw_sensitivity:
            assert len(entry.elts) == 2
            edge_node, signal_name_node = entry.elts
            if isinstance(edge_node, ast.Name):
                edge_type = edge_node.id
            else:
                edge_type = edge_node.attr
            edge_type = edge_type.capitalize()
            if isinstance(signal_name_node, ast.Name):
                name = signal_name_node.id
                assert name in local, "{0} not found".format(name)
                n = eval(name, local)
                assert isinstance(n, _kratos.Var), \
                    "{0} is not a variable".format(name)
                signal_name = str(n)
            elif isinstance(signal_name_node, ast.Attribute):
                # need to eval the actual name
                n = eval(astor.to_source(signal_name_node), local)
                assert isinstance(n, _kratos.Var), \
                    "{0} is not a variable".format(signal_name_node)
                signal_name = str(n)
            else:
                signal_name = signal_name_node.s
            result.append((edge_type, signal_name))
        return blk_type, result


def get_ln(fn):
    info = inspect.getsourcelines(fn)
    return info[1]


def get_fn(fn):
    return os.path.abspath(inspect.getsourcefile(fn))
