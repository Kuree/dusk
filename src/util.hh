#ifndef KRATOS_UTIL_HH
#define KRATOS_UTIL_HH

#include "expr.hh"
#include "stmt.hh"
#include "port.hh"

namespace kratos {

uint32_t get_num_cpus();
void set_num_cpus(int num_cpu);

std::string ExprOpStr(ExprOp op);

// may need to look at this https://stackoverflow.com/q/28828957
std::string var_type_to_string(VarType type);

std::string ast_type_to_string(IRNodeKind kind);

std::string assign_type_to_str(AssignmentType type);

std::string port_dir_to_str(PortDirection direction);

std::string port_type_to_str(PortType type);

bool is_valid_verilog(const std::string &src);

bool is_valid_verilog(const std::map<std::string, std::string> &src);

void remove_stmt_from_parent(const std::shared_ptr<Stmt> &stmt);

std::vector<std::string> get_tokens(const std::string &line, const std::string &delimiter);

std::map<std::string, std::shared_ptr<Port>> get_port_from_verilog(Generator *generator,
                                                                   const std::string &src,
                                                                   const std::string &top_name);

namespace fs {
std::string join(const std::string &path1, const std::string &path2);
std::string which(const std::string &name);
bool exists(const std::string &filename);
bool remove(const std::string &filename);
std::string temp_directory_path();
}  // namespace fs
}  // namespace kratos

#endif  // KRATOS_UTIL_HH
