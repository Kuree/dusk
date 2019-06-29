#include "expr.hh"
#include <iostream>
#include <stdexcept>
#include "fmt/format.h"
#include "generator.hh"
#include "stmt.hh"
#include "util.hh"

using fmt::format;
using std::make_shared;
using std::runtime_error;
using std::shared_ptr;
using std::string;
using std::vector;

bool is_relational_op(ExprOp op) {
    static std::unordered_set<ExprOp> ops = {ExprOp::LessThan, ExprOp::GreaterThan,
                                             ExprOp::LessEqThan, ExprOp::GreaterEqThan, ExprOp::Eq};
    return ops.find(op) != ops.end();
}

std::pair<std::shared_ptr<Var>, std::shared_ptr<Var>> Var::get_binary_var_ptr(
    const Var &var) const {
    auto left = generator->get_var(name);
    if (left == nullptr)
        throw std::runtime_error(
            ::format("unable to find port {0} from {1}", var.name, var.generator->name));
    auto right = generator->get_var(var.name);
    if (right == nullptr)
        throw std::runtime_error(
            ::format("unable to find port {0} from {1}", var.name, var.generator->name));
    return {left, right};
}

Expr &Var::operator-(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::Minus, left, right);
}

Expr &Var::operator-() const {
    auto var = generator->get_var(name);
    return generator->expr(ExprOp::Minus, var, nullptr);
}

Expr &Var::operator~() const {
    auto var = generator->get_var(name);
    return generator->expr(ExprOp::UInvert, var, nullptr);
}

Expr &Var::operator+() const {
    auto var = generator->get_var(name);
    return generator->expr(ExprOp::UPlus, var, nullptr);
}

Expr &Var::operator+(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::Add, left, right);
}

Expr &Var::operator*(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::Multiply, left, right);
}

Expr &Var::operator%(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::Mod, left, right);
}

Expr &Var::operator/(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::Divide, left, right);
}

Expr &Var::operator>>(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::LogicalShiftRight, left, right);
}

Expr &Var::operator<<(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::ShiftLeft, left, right);
}

Expr &Var::operator|(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::Or, left, right);
}

Expr &Var::operator&(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::And, left, right);
}

Expr &Var::operator^(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::Xor, left, right);
}

Expr &Var::ashr(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::SignedShiftRight, left, right);
}

Expr &Var::operator<(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::LessThan, left, right);
}

Expr &Var::operator>(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::GreaterThan, left, right);
}

Expr &Var::operator<=(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::LessEqThan, left, right);
}

Expr &Var::operator>=(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::GreaterEqThan, left, right);
}

Expr &Var::eq(const Var &var) const {
    const auto &[left, right] = get_binary_var_ptr(var);
    return generator->expr(ExprOp::Eq, left, right);
}

VarSlice &Var::operator[](std::pair<uint32_t, uint32_t> slice) {
    auto const [high, low] = slice;
    if (low > high) {
        throw ::runtime_error(::format("low ({0}) cannot be larger than ({1})", low, high));
    }
    if (high >= width) {
        throw ::runtime_error(
            ::format("high ({0}) has to be smaller than width ({1})", high, width));
    }
    // if we already has the slice
    if (slices_.find(slice) != slices_.end()) return *slices_.at(slice);
    // create a new one
    // notice that slice is not part of generator's variables. It's handled by the parent (var)
    // itself
    auto var_slice = ::make_shared<VarSlice>(this, high, low);
    slices_.emplace(slice, var_slice);
    return *slices_.at(slice);
}

VarConcat &Var::concat(Var &var) {
    auto ptr = var.shared_from_this();
    // notice that we effectively created an implicit sink->sink by creating a concat
    // however, it's not an assignment, that's why we need to use concat_vars to hold the
    // vars
    for (auto const &exist_var : concat_vars_) {
        // reuse the existing variables
        if (exist_var->vars.size() == 2 && exist_var->vars.back() == ptr) {
            return *exist_var;
        }
    }
    auto concat_ptr = std::make_shared<VarConcat>(generator, shared_from_this(), ptr);
    concat_vars_.emplace(concat_ptr);
    return *concat_ptr;
}

std::string Var::to_string() const { return name; }

VarSlice &Var::operator[](uint32_t bit) { return (*this)[{bit, bit}]; }

VarSlice::VarSlice(Var *parent, uint32_t high, uint32_t low)
    : Var(parent->generator, "", high - low + 1, parent->is_signed, VarType::Slice),
      parent_var(parent),
      low(low),
      high(high) {}

std::string VarSlice::get_slice_name(const std::string &parent_name, uint32_t high, uint32_t low) {
    return ::format("{0}[{1}:{2}]", parent_name, high, low);
}

std::string VarSlice::to_string() const {
    return get_slice_name(parent_var->to_string(), high, low);
}

Expr::Expr(ExprOp op, const ::shared_ptr<Var> &left, const ::shared_ptr<Var> &right)
    : op(op), left(left), right(right) {
    if (left == nullptr) throw std::runtime_error("left operand is null");
    if (right != nullptr && left->generator != right->generator)
        throw std::runtime_error(
            ::format("{0} context is different from that of {1}'s", left->name, right->name));
    generator = left->generator;
    if (right != nullptr && left->width != right->width)
        throw std::runtime_error(
            ::format("left ({0}) width ({1}) doesn't match with right ({2}) width ({3})",
                     left->name, left->width, right->name, right->width));
    // if it's a predicate/relational op, the width is one
    if (is_relational_op(op))
        width = 1;
    else
        width = left->width;

    if (right != nullptr)
        name = ::format("({0} {1} {2})", left->name, ExprOpStr(op), right->name);
    else
        name = ::format("({0} {1})", ExprOpStr(op), left->name);
    if (right != nullptr)
        is_signed = left->is_signed & right->is_signed;
    else
        is_signed = left->is_signed;
    type_ = VarType::Expression;
}

Var::Var(Generator *module, const std::string &name, uint32_t width, bool is_signed)
    : Var(module, name, width, is_signed, VarType::Base) {}

Var::Var(Generator *module, const std::string &name, uint32_t width, bool is_signed, VarType type)
    : ASTNode(ASTNodeKind::VarKind),
      name(name),
      width(width),
      is_signed(is_signed),
      generator(module),
      type_(type) {
    if (module == nullptr) throw ::runtime_error(::format("module is null for {0}", name));
}

ASTNode *Var::parent() { return generator; }
ASTNode *VarSlice::parent() { return parent_var; }

AssignStmt &Var::assign(const std::shared_ptr<Var> &var) {
    return assign(var, AssignmentType::Undefined);
}

AssignStmt &Var::assign(Var &var) { return assign(var, AssignmentType::Undefined); }

AssignStmt &Var::assign(const std::shared_ptr<Var> &var, AssignmentType type) {
    // if it's a constant or expression, it can't be assigned to
    if (type_ == VarType::ConstValue)
        throw ::runtime_error(::format("Cannot assign {0} to a const {1}", var->name, name));
    else if (type_ == VarType::Expression)
        throw ::runtime_error(::format("Cannot assign {0} to an expression", var->name, name));
    auto const &stmt = ::make_shared<AssignStmt>(shared_from_this(), var, type);
    // determine the type
    AssignmentType self_type = AssignmentType::Undefined;
    for (auto const &sink : sinks_) {
        if (sink->assign_type() != AssignmentType::Undefined) {
            self_type = sink->assign_type();
            break;
        }
    }
    // this is effectively an SSA implementation here
    for (auto &exist_stmt : var->sinks_) {
        if (exist_stmt->equal(stmt)) {
            // check if the assign statement type match
            if (exist_stmt->assign_type() == AssignmentType::Undefined &&
                type == AssignmentType::Blocking)
                exist_stmt->set_assign_type(type);
            else if (exist_stmt->assign_type() == AssignmentType::Undefined &&
                     type == AssignmentType::NonBlocking)
                exist_stmt->set_assign_type(type);
            else if (type != AssignmentType::Undefined && exist_stmt->assign_type() != type)
                throw ::runtime_error("Assignment type mismatch with existing one");
            return *exist_stmt;
        }
    }
    // push the stmt into its sources
    var->add_sink(stmt);
    add_source(stmt);
    if (self_type == AssignmentType::Undefined) self_type = type;
    // check if the assignment match existing ones. if existing ones are unknown
    // assign them
    for (auto const &sink : var->sinks_) {
        if (sink->assign_type() == AssignmentType::Undefined)
            sink->set_assign_type(self_type);
        else if (sink->assign_type() != self_type)
            throw ::runtime_error(
                ::format("{0}'s assignment type ({1}) does not match with {2}'s {3}", var->name,
                assign_type_to_str(sink->assign_type()), name, assign_type_to_str(self_type)));
    }
    return *stmt;
}

void Var::unassign(const std::shared_ptr<Var> &var) {
    // FIXME make it more efficient
    auto stmt = assign(var).shared_from_this()->as<AssignStmt>();
    var->sinks_.erase(stmt);
    sources_.erase(stmt);
    // erase from parent if any
    generator->remove_stmt(stmt);
}

Const::Const(Generator *generator, int64_t value, uint32_t width, bool is_signed)
    : Var(generator, "", width, is_signed, VarType::ConstValue), value_() {
    // need to deal with the signed value
    if (is_signed) {
        // compute the -max value
        uint64_t temp = (~0ull) << (width - 1);
        int64_t min = 0;
        std::memcpy(&min, &temp, sizeof(min));
        if (value < min)
            throw ::runtime_error(::format(
                "{0} is smaller than the minimum value ({1}) given width {2}", value, min, width));
        temp = (1ull << (width - 1)) - 1;
        int64_t max;
        std::memcpy(&max, &temp, sizeof(max));
        if (value > max)
            throw ::runtime_error(::format(
                "{0} is larger than the maximum value ({1}) given width {2}", value, max, width));
    } else {
        uint64_t max = (1ull << width) - 1;
        uint64_t unsigned_value;
        std::memcpy(&unsigned_value, &value, sizeof(unsigned_value));
        if (unsigned_value > max)
            throw ::runtime_error(::format(
                "{0} is larger than the maximum value ({1}) given width {2}", value, max, width));
    }
    value_ = value;
}

VarSigned::VarSigned(Var *parent)
    : Var(parent->generator, "", parent->width, true, parent->type()), parent_var_(parent) {}

AssignStmt &VarSigned::assign(const std::shared_ptr<Var> &, AssignmentType) {
    throw ::runtime_error(::format("{0} is not allowed to be a sink", to_string()));
}

std::string VarSigned::to_string() const {
    return ::format("$signed({0})", parent_var_->to_string());
}

void VarSigned::add_sink(const std::shared_ptr<AssignStmt> &stmt) { parent_var_->add_sink(stmt); }

std::shared_ptr<Var> Var::signed_() {
    if (is_signed) {
        return shared_from_this();
    } else if (signed_self_) {
        return signed_self_;
    } else {
        signed_self_ = std::make_shared<VarSigned>(this);
        return signed_self_;
    }
}

void Const::set_value(int64_t new_value) {
    try {
        Const c(generator, new_value, width, is_signed);
        value_ = new_value;
    } catch (::runtime_error &) {
        std::cerr << ::format("Unable to set value from {0} to {1}", value_, new_value)
                  << std::endl;
    }
}

VarConcat::VarConcat(Generator *m, const std::shared_ptr<Var> &first,
                     const std::shared_ptr<Var> &second)
    : Var(m, "", first->width + second->width, first->is_signed && second->is_signed,
          VarType::Expression) {
    vars.emplace_back(first);
    vars.emplace_back(second);
}

VarConcat &VarConcat::concat(Var &var) {
    std::shared_ptr<VarConcat> new_var = std::make_shared<VarConcat>(*this);
    new_var->vars.emplace_back(var.shared_from_this());
    new_var->width += var.width;
    // update the upstream vars about linking
    for (auto &var_ptr : new_var->vars) {
        var_ptr->add_concat_var(new_var);
    }
    return *new_var;
}

std::string VarConcat::to_string() const {
    std::vector<std::string> var_names;
    for (const auto &ptr : vars) var_names.emplace_back(ptr->to_string());
    auto content = fmt::join(var_names.begin(), var_names.end(), ", ");
    return ::format("{{{0}}}", content);
}

VarConcat::VarConcat(const VarConcat &var)
    : Var(var.generator, var.name, var.width, var.is_signed) {
    vars = std::vector<std::shared_ptr<Var>>(var.vars.begin(), var.vars.end());
}

std::string Const::to_string() const {
    if (is_signed && value_ < 0) {
        return ::format("-{0}'h{1:X}", width, -value_);
    } else {
        return ::format("{0}'h{1:X}", width, value_);
    }
}

AssignStmt &Var::assign(Var &var, AssignmentType type) {
    // need to find the pointer
    auto var_ptr = var.shared_from_this();
    return assign(var_ptr, type);
}

std::string Expr::to_string() const {
    if (right != nullptr) {
        return ::format("{0} {1} {2}", left->name, ExprOpStr(op), right->name);
    } else {
        return ::format("{0}{1}", ExprOpStr(op), left->name);
    }
}

ASTNode *Expr::get_child(uint64_t index) {
    if (index == 0)
        return left.get();
    else if (index == 1)
        return right ? right.get() : nullptr;
    else
        return nullptr;
}

void Var::move_src_to(Var *var, Var *new_var, Generator *parent) {
    // only base and port vars are allowed
    if (var->type_ == VarType::Expression || var->type_ == VarType::ConstValue)
        throw ::runtime_error("Only base or port variables are allowed.");

    for (auto &stmt : var->sources_) {
        if (stmt->left() != var->shared_from_this())
            throw ::runtime_error("Var assignment is wrong.");
        stmt->set_left(new_var->shared_from_this());
        new_var->sources_.emplace(stmt);
    }

    // need to deal with slices as well
    for (auto &[slice, slice_var] : var->slices_) {
        auto &new_var_slice = (*new_var)[slice];
        move_src_to(slice_var.get(), &new_var_slice, parent);
    }
    // create an assignment and add it to the parent
    auto &stmt = var->assign(new_var->shared_from_this());
    parent->add_stmt(stmt.shared_from_this());
}

void Var::move_sink_to(Var *var, Var *new_var, Generator *parent) {
    // only base and port vars are allowed
    if (var->type_ == VarType::Expression || var->type_ == VarType::ConstValue)
        throw ::runtime_error("Only base or port variables are allowed.");

    for (auto &stmt : var->sinks_) {
        if (stmt->right() != var->shared_from_this())
            throw ::runtime_error("Var assignment is wrong.");
        stmt->set_right(new_var->shared_from_this());
        new_var->sinks_.emplace(stmt);
    }

    // need to deal with slices as well
    for (auto &[slice, slice_var] : var->slices_) {
        auto &new_var_slice = (*new_var)[slice];
        move_sink_to(slice_var.get(), &new_var_slice, parent);
    }

    // create an assignment and add it to the parent
    auto &stmt = new_var->assign(var->shared_from_this());
    parent->add_stmt(stmt.shared_from_this());
}