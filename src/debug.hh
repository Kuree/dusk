#ifndef KRATOS_DEBUG_HH
#define KRATOS_DEBUG_HH

#include "stmt.hh"

namespace kratos {

constexpr char break_point_func_name[] = "breakpoint_trace";
constexpr char break_point_func_arg[] = "stmt_id";

void inject_debug_break_points(Generator *top);
std::map<Stmt *, uint32_t> extract_debug_break_points(Generator *top);

// for verilator
void insert_verilator_public(Generator *top);

class DebugDatabase {
public:
    using ConnectionMap =
        std::map<std::pair<std::string, std::string>, std::pair<std::string, std::string>>;

    DebugDatabase() = default;
    explicit DebugDatabase(std::string top_name) : top_name_(std::move(top_name)) {}

    void set_break_points(Generator *top);
    void set_break_points(Generator *top, const std::string &ext);

    // these have to be called after unification happens
    void set_generator_connection(Generator *top);
    void set_generator_hierarchy(Generator *top);

    void set_variable_mapping(const std::map<Generator *, std::map<std::string, Var *>> &mapping);

    void save_database(const std::string &filename);

private:
    std::map<Stmt *, uint32_t> break_points_;
    std::unordered_map<Generator *, std::set<uint32_t>> generator_break_points_;
    std::map<Stmt *, std::pair<std::string, uint32_t>> stmt_mapping_;
    std::unordered_map<std::string, std::pair<Generator *, std::map<std::string, std::string>>>
        variable_mapping_;
    ConnectionMap connection_map_;
    std::vector<std::pair<std::string, std::string>> hierarchy_;

    std::string top_name_ = "TOP";
};


// table row definitions
struct MetaData {
    std::string name;
    std::string value;
};

struct BreakPoint {
    uint32_t id;
    std::string filename;
    uint32_t line_num;
};

struct Variable {
    std::string handle;
    std::string var;
    std::string front_var;
    uint32_t id;
};

struct Connection {
    std::string handle_from;
    std::string var_from;
    std::string handle_to;
    std::string var_to;
};

struct Hierarchy {
    std::string parent_handle;
    std::string child;
};

// initialize the database
auto init_storage(const std::string &filename);

}  // namespace kratos
#endif  // KRATOS_DEBUG_HH
