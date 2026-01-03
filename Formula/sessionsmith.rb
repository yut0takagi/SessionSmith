class Sessionsmith < Formula
  desc "Git-style session management for Python. Save, restore, and track your variables with ease."
  homepage "https://github.com/yut0takagi/SessionSmith"
  url "https://github.com/yut0takagi/SessionSmith/archive/refs/tags/v2.0.0.tar.gz"
  sha256 ""  # GitHub Actionsで自動更新されます
  license "MIT"
  head "https://github.com/yut0takagi/SessionSmith.git", branch: "main"

  depends_on "python@3.9"

  def install
    system "python3", "-m", "pip", "install", *std_pip_args, "."
  end

  test do
    system "#{bin}/ssm", "--version"
  end
end

