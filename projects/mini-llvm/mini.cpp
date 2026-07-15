//===----------------------------------------------------------------------===//
// mini.cpp — 極簡教學編譯器 v2：標準遞迴下降版
//
// 語言範例（program.mini）：
//     a = 5
//     b = 7
//     c = a + b + 2        ← 加法鏈（左結合）
//     d = (a + b) + c      ← 括號 = 巢狀 = 遞迴的來源
//     return d
//
// 文法（每條規則 = 下面一個 parseXxx 函式，一一對應）：
//     program := stmt*
//     stmt    := IDENT '=' expr  |  'return' expr
//     expr    := term ('+' term)*          ← 加法鏈
//     term    := NUMBER | IDENT | '(' expr ')'   ← 括號讓 term 又呼叫 expr：遞迴！
//
// 呼叫關係（遞迴下降的「遞迴」就在這個環）：
//     parseStmt ──> parseExpr ──> parseTerm ──┐
//                       ▲                     │ 遇到 '('
//                       └─────────────────────┘
//
// 編譯： bash build.sh
// 執行： ./mini program.mini            （印 tokens、AST、IR）
//        ./mini program.mini --trace    （加印 parser 遞迴過程，step by step）
// 跑IR： /usr/lib/llvm-20/bin/lli out.ll ; echo $?
//===----------------------------------------------------------------------===//

#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Verifier.h"
#include "llvm/Support/raw_ostream.h"
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <vector>

//===--------------------------------------------------------------------===//
// [1] LEXER — 字元流 → token 流（v2 多了左右括號，共 8 種）
//===--------------------------------------------------------------------===//

enum TokenKind { TK_IDENT, TK_NUMBER, TK_EQUAL, TK_PLUS,
                 TK_LPAREN, TK_RPAREN, TK_RETURN, TK_EOF };
static const char *TOKEN_NAMES[] = {"IDENT", "NUMBER", "EQUAL", "PLUS",
                                    "LPAREN", "RPAREN", "RETURN", "EOF"};

struct Token { TokenKind kind; std::string text; };

std::vector<Token> lex(const std::string &src) {
    std::vector<Token> toks;
    size_t i = 0;
    while (i < src.size()) {
        char c = src[i];
        if (isspace(c)) { i++; continue; }
        if (isdigit(c)) {
            std::string num;
            while (i < src.size() && isdigit(src[i])) num += src[i++];
            toks.push_back({TK_NUMBER, num});
        } else if (isalpha(c)) {
            std::string id;
            while (i < src.size() && isalnum(src[i])) id += src[i++];
            toks.push_back({id == "return" ? TK_RETURN : TK_IDENT, id});
        } else if (c == '=') { toks.push_back({TK_EQUAL,  "="}); i++; }
        else if (c == '+')   { toks.push_back({TK_PLUS,   "+"}); i++; }
        else if (c == '(')   { toks.push_back({TK_LPAREN, "("}); i++; }
        else if (c == ')')   { toks.push_back({TK_RPAREN, ")"}); i++; }
        else { std::cerr << "lex error: '" << c << "'\n"; exit(1); }
    }
    toks.push_back({TK_EOF, ""});
    return toks;
}

//===--------------------------------------------------------------------===//
// [2] AST — v2 的運算式是「真正的樹」
//
// v1 的 Expr 是攤平的 struct；現在 Add 的左右手是 Expr 指標，
// 所以 (a+b)+c 長成：      Add
//                         /   \
//                       Add    Var(c)
//                      /   \
//                  Var(a)  Var(b)
//===--------------------------------------------------------------------===//

struct Expr {
    enum Kind { NUM, VAR, ADD } kind;
    int num = 0;                        // NUM
    std::string name;                   // VAR
    std::unique_ptr<Expr> lhs, rhs;     // ADD 的左右子樹

    static std::unique_ptr<Expr> mkNum(int v) {
        auto e = std::make_unique<Expr>(); e->kind = NUM; e->num = v; return e;
    }
    static std::unique_ptr<Expr> mkVar(std::string n) {
        auto e = std::make_unique<Expr>(); e->kind = VAR; e->name = std::move(n); return e;
    }
    static std::unique_ptr<Expr> mkAdd(std::unique_ptr<Expr> l, std::unique_ptr<Expr> r) {
        auto e = std::make_unique<Expr>(); e->kind = ADD;
        e->lhs = std::move(l); e->rhs = std::move(r); return e;
    }
};

struct Stmt {
    enum { ASSIGN, RETURN } kind;
    std::string target;                 // ASSIGN 的左邊變數
    std::unique_ptr<Expr> expr;         // ASSIGN 右邊 / RETURN 的運算式
};

// 印 AST（前序走訪，括號呈現樹形）
std::string exprToStr(const Expr *e) {
    switch (e->kind) {
    case Expr::NUM: return "Num(" + std::to_string(e->num) + ")";
    case Expr::VAR: return "Var(" + e->name + ")";
    case Expr::ADD: return "Add(" + exprToStr(e->lhs.get()) + ", "
                                  + exprToStr(e->rhs.get()) + ")";
    }
    return "?";
}

//===--------------------------------------------------------------------===//
// [3] PARSER — 標準遞迴下降：一條文法規則 = 一個函式
//
// 用 class 包住是為了共享兩個狀態：token 游標 pos、trace 縮排深度。
// 每個 parseXxx 進入時「已知第一個 token 屬於這條規則」，
// 離開時游標停在規則結束的下一個 token — 這是遞迴下降的黃金約定。
//===--------------------------------------------------------------------===//

class Parser {
    const std::vector<Token> &toks;
    size_t pos = 0;
    bool trace;
    int depth = 0;                      // 只給 trace 縮排用

    const Token &peek() { return toks[pos]; }
    Token eat(TokenKind k, const char *what) {
        if (peek().kind != k) {
            std::cerr << "parse error: expected " << what
                      << ", got '" << peek().text << "'\n"; exit(1);
        }
        return toks[pos++];
    }
    // trace 小工具：進出函式時印出「現在在哪、看到什麼 token」
    void enter(const char *fn) {
        if (trace) std::cout << std::string(depth * 2, ' ') << "→ " << fn
                             << "  (下一個 token: " << TOKEN_NAMES[peek().kind]
                             << " '" << peek().text << "')\n";
        depth++;
    }
    void leave(const char *fn, const std::string &made) {
        depth--;
        if (trace) std::cout << std::string(depth * 2, ' ') << "← " << fn
                             << "  做出 " << made << "\n";
    }

public:
    Parser(const std::vector<Token> &t, bool tr) : toks(t), trace(tr) {}

    // program := stmt*
    std::vector<Stmt> parseProgram() {
        std::vector<Stmt> prog;
        while (peek().kind != TK_EOF)
            prog.push_back(parseStmt());
        return prog;
    }

    // stmt := IDENT '=' expr | 'return' expr
    Stmt parseStmt() {
        enter("parseStmt");
        Stmt s;
        if (peek().kind == TK_RETURN) {
            eat(TK_RETURN, "'return'");
            s.kind = Stmt::RETURN;
            s.expr = parseExpr();                       // ← 呼叫下一層規則
        } else {
            Token name = eat(TK_IDENT, "identifier");
            eat(TK_EQUAL, "'='");
            s.kind = Stmt::ASSIGN;
            s.target = name.text;
            s.expr = parseExpr();                       // ← 呼叫下一層規則
        }
        leave("parseStmt", s.kind == Stmt::RETURN ? "Return" : "Assign(" + s.target + ")");
        return s;
    }

    // expr := term ('+' term)*
    // 「先拿一個 term，只要後面還有 + 就再拿一個 term 掛上去」
    // 左結合：a+b+c 組成 Add(Add(a,b),c) — 樹往左長
    std::unique_ptr<Expr> parseExpr() {
        enter("parseExpr");
        auto lhs = parseTerm();                         // ← 呼叫下一層規則
        while (peek().kind == TK_PLUS) {
            eat(TK_PLUS, "'+'");
            auto rhs = parseTerm();
            lhs = Expr::mkAdd(std::move(lhs), std::move(rhs));
        }
        leave("parseExpr", exprToStr(lhs.get()));
        return lhs;
    }

    // term := NUMBER | IDENT | '(' expr ')'
    // 第三個分支就是「遞迴」發生的地方：term 又呼叫回 expr。
    // 括號巢狀多深，parseTerm→parseExpr→parseTerm→... 就疊多深。
    std::unique_ptr<Expr> parseTerm() {
        enter("parseTerm");
        std::unique_ptr<Expr> e;
        if (peek().kind == TK_NUMBER) {
            e = Expr::mkNum(std::stoi(eat(TK_NUMBER, "number").text));
        } else if (peek().kind == TK_IDENT) {
            e = Expr::mkVar(eat(TK_IDENT, "identifier").text);
        } else if (peek().kind == TK_LPAREN) {
            eat(TK_LPAREN, "'('");
            e = parseExpr();                            // ★ 遞迴：回到上一層規則
            eat(TK_RPAREN, "')'");
        } else {
            std::cerr << "parse error: unexpected '" << peek().text << "'\n"; exit(1);
        }
        leave("parseTerm", exprToStr(e.get()));
        return e;
    }
};

//===--------------------------------------------------------------------===//
// [4] CODEGEN — 遞迴走訪 AST，IRBuilder 吐 LLVM IR
//
// parser 是「照文法遞迴」，codegen 是「照樹形遞迴」：
// codegenExpr(Add) = 先生左子樹的值、再生右子樹的值、最後 CreateAdd。
// 變數維持 clang -O0 策略：alloca / store / load，SSA 化交給 mem2reg。
//===--------------------------------------------------------------------===//

struct Codegen {
    llvm::LLVMContext ctx;
    llvm::Module mod{"mini", ctx};
    llvm::IRBuilder<> builder{ctx};
    std::map<std::string, llvm::Value *> vars;   // 變數名 → alloca 位置

    llvm::Value *slot(const std::string &name) {
        if (!vars.count(name))
            vars[name] = builder.CreateAlloca(builder.getInt32Ty(), nullptr, name);
        return vars[name];
    }

    // 後序走訪：先算子樹、再組合 — 跟手算算式的順序一樣
    llvm::Value *codegenExpr(const Expr *e) {
        switch (e->kind) {
        case Expr::NUM: return builder.getInt32(e->num);
        case Expr::VAR: return builder.CreateLoad(builder.getInt32Ty(),
                                                  slot(e->name), e->name);
        case Expr::ADD: {
            llvm::Value *l = codegenExpr(e->lhs.get());  // ← 遞迴左子樹
            llvm::Value *r = codegenExpr(e->rhs.get());  // ← 遞迴右子樹
            return builder.CreateAdd(l, r, "addtmp");
        }
        }
        return nullptr;
    }

    void run(const std::vector<Stmt> &prog) {
        auto *fnTy = llvm::FunctionType::get(builder.getInt32Ty(), {}, false);
        auto *mainFn = llvm::Function::Create(
            fnTy, llvm::Function::ExternalLinkage, "main", mod);
        builder.SetInsertPoint(llvm::BasicBlock::Create(ctx, "entry", mainFn));

        for (auto &s : prog) {
            llvm::Value *v = codegenExpr(s.expr.get());
            if (s.kind == Stmt::ASSIGN)
                builder.CreateStore(v, slot(s.target));
            else
                builder.CreateRet(v);
        }
    }
};

//===--------------------------------------------------------------------===//
// main — 四站串起來
//===--------------------------------------------------------------------===//

int main(int argc, char **argv) {
    std::string path = "program.mini";
    bool trace = false;
    for (int i = 1; i < argc; i++) {
        if (std::string(argv[i]) == "--trace") trace = true;
        else path = argv[i];
    }

    std::ifstream f(path);
    if (!f) { std::cerr << "cannot open " << path << "\n"; return 1; }
    std::stringstream ss; ss << f.rdbuf();
    std::string src = ss.str();
    std::cout << "═══ 原始碼 ═══\n" << src << "\n";

    auto toks = lex(src);
    std::cout << "═══ [1] Tokens ═══\n";
    for (auto &t : toks)
        std::cout << "  (" << TOKEN_NAMES[t.kind] << ", '" << t.text << "')\n";

    std::cout << "\n═══ [2] Parser" << (trace ? "（--trace 遞迴過程）" : "")
              << " ═══\n";
    Parser parser(toks, trace);
    auto prog = parser.parseProgram();
    std::cout << "\n═══ AST ═══\n";
    for (auto &s : prog) {
        if (s.kind == Stmt::RETURN)
            std::cout << "  Return(" << exprToStr(s.expr.get()) << ")\n";
        else
            std::cout << "  Assign(" << s.target << ", "
                      << exprToStr(s.expr.get()) << ")\n";
    }

    Codegen cg;
    cg.run(prog);
    if (llvm::verifyModule(cg.mod, &llvm::errs())) return 1;

    std::cout << "\n═══ [3] LLVM IR ═══\n";
    std::cout.flush();
    cg.mod.print(llvm::outs(), nullptr);
    llvm::outs().flush();

    std::error_code ec;
    llvm::raw_fd_ostream out("out.ll", ec);
    cg.mod.print(out, nullptr);
    std::cout << "\n已存 out.ll — 接著玩：\n"
              << "  跑起來:   /usr/lib/llvm-20/bin/lli out.ll ; echo $?\n"
              << "  看SSA化:  /usr/lib/llvm-20/bin/opt -passes=mem2reg -S out.ll\n";
    return 0;
}
