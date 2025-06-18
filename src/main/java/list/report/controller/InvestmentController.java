package list.report.controller;

import list.report.dto.InvestmentReportItem;
import list.report.service.InvestmentReportService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/reports")
public class InvestmentController {

    private final InvestmentReportService investmentReportService;

    @Autowired
    public InvestmentController(InvestmentReportService investmentReportService) {
        this.investmentReportService = investmentReportService;
    }

    @GetMapping("/investment")
    public List<InvestmentReportItem> getInvestmentReports() {
        return investmentReportService.fetchInvestmentReports();
    }
}
