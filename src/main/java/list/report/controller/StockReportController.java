package list.report.controller;

import list.report.dto.StockReportItem;
import list.report.service.StockReportService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/reports")
public class StockReportController {

    private final StockReportService stockReportService;

    @Autowired
    public StockReportController(StockReportService stockReportService){
        this.stockReportService = stockReportService;
    }

    @GetMapping("/stocks")
    public List<StockReportItem> getTop10StockReports(){
        return stockReportService.fetchStockReports();
    }

}
